/**
 * Generic reverse proxy: mounts `${prefix}/*` and forwards 1:1 to `upstream`,
 * injecting trusted identity headers derived from the gateway's own JWT
 * verification (downstream services trust these — they never see the token).
 *
 * Add one call per service as it comes online, e.g.:
 *   registerServiceProxy(app, { prefix: "/v1/customers", upstream: config.customerServiceUrl });
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { injectTraceHeaders } from "./observability.js";
import { recordIdentityHeaderSpoofing } from "./security-metrics.js";

const HOP_BY_HOP_HEADERS = new Set(["host", "connection", "content-length", "transfer-encoding"]);

export interface ServiceProxyOptions {
  prefix: string;
  upstream: string;
  /**
   * Max request body this prefix will buffer, in bytes. Omit to inherit
   * Fastify's 1 MiB default, which is right for every JSON-only service.
   *
   * Set this ONLY on prefixes that actually receive file uploads. A
   * route-level bodyLimit overrides the catch-all parser's limit
   * unconditionally (verified against Fastify 5.10 — the route wins in both
   * directions, whether it raises or lowers), so this is the single knob
   * that decides how many bytes an unauthenticated caller can make the
   * gateway hold before it rejects them.
   */
  bodyLimit?: number;
}

export function registerServiceProxy(app: FastifyInstance, opts: ServiceProxyOptions): void {
  const handler = async (request: FastifyRequest, reply: FastifyReply) => {
    const target = new URL(request.url, opts.upstream);

    const headers: Record<string, string> = {};
    for (const [key, value] of Object.entries(request.headers)) {
      if (typeof value === "string" && !HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
        headers[key] = value;
      }
    }
    headers["x-request-id"] = String(request.id);
    // A no-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset — see observability.ts.
    injectTraceHeaders(request, headers);
    // Observe before stripping (T310b). The strip below is what keeps tenants
    // apart; this call is what makes the attempt visible. It MUST stay above
    // the deletes — afterwards there is nothing left to observe, and a caller
    // could enumerate every tenant id in the platform leaving no trace. Locked
    // by tests/security/test_security_invariants.py.
    recordIdentityHeaderSpoofing(request);
    // Strip any client-supplied identity headers unconditionally before the
    // auth block (re-)populates them. Most routes require request.auth (so
    // this is normally a no-op — the block below always overwrites), but on
    // public routes (e.g. GET /v1/proposals/{id}/view) request.auth is
    // undefined and these must never reach the upstream from the caller.
    delete headers["x-tenant-id"];
    delete headers["x-user-id"];
    delete headers["x-user-roles"];
    // Overwrite (never append to) any client-supplied x-forwarded-for with the
    // real peer address. esign-service records this as the signer's IP in a
    // legal audit trail (M10/T204), so a caller must not be able to choose
    // what gets written there. Same reasoning as the identity headers above.
    headers["x-forwarded-for"] = request.ip;
    if (request.auth) {
      headers["x-tenant-id"] = request.auth.tid;
      headers["x-user-id"] = request.auth.sub;
      headers["x-user-roles"] = request.auth.roles.join(",");
    }

    const hasBody = !["GET", "HEAD"].includes(request.method);
    // A Buffer means the body came through the catch-all content-type parser
    // (registered in server.ts) - i.e. it's something Fastify has no built-in
    // parser for, such as multipart/form-data - and must be forwarded as raw
    // bytes. Anything else is an already-parsed object (JSON) and keeps the
    // existing JSON.stringify behavior.
    const body = hasBody
      ? Buffer.isBuffer(request.body)
        ? request.body
        : JSON.stringify(request.body ?? {})
      : undefined;
    const upstreamResponse = await fetch(target, {
      method: request.method,
      headers,
      body,
    });

    reply.code(upstreamResponse.status);
    const contentType = upstreamResponse.headers.get("content-type");
    if (contentType) reply.header("content-type", contentType);
    // Buffer, not .text() — .text() UTF-8-decodes the body, which silently
    // corrupts binary responses (PDFs). Buffer round-trips both binary and
    // text content correctly.
    reply.send(Buffer.from(await upstreamResponse.arrayBuffer()));
  };

  // Only pass bodyLimit when set — `{ bodyLimit: undefined }` is not the same
  // as omitting it to Fastify's route validator.
  const routeOptions = opts.bodyLimit === undefined ? {} : { bodyLimit: opts.bodyLimit };

  // find-my-way's wildcard (`prefix/*`) does not match the bare prefix with
  // no trailing segment, so both must be registered explicitly to cover
  // list/create calls like `GET /v1/quotes` or `POST /v1/customers`.
  // Both get the same bodyLimit: a limit applied to only one of the two is
  // the same class of half-registered-route bug T203 fixed here.
  app.all(opts.prefix, routeOptions, handler);
  app.all(`${opts.prefix}/*`, routeOptions, handler);
}
