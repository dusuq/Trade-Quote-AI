/**
 * Generic reverse proxy: mounts `${prefix}/*` and forwards 1:1 to `upstream`,
 * injecting trusted identity headers derived from the gateway's own JWT
 * verification (downstream services trust these — they never see the token).
 *
 * Add one call per service as it comes online, e.g.:
 *   registerServiceProxy(app, { prefix: "/v1/customers", upstream: config.customerServiceUrl });
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";

const HOP_BY_HOP_HEADERS = new Set(["host", "connection", "content-length", "transfer-encoding"]);

export interface ServiceProxyOptions {
  prefix: string;
  upstream: string;
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
    if (request.auth) {
      headers["x-tenant-id"] = request.auth.tid;
      headers["x-user-id"] = request.auth.sub;
      headers["x-user-roles"] = request.auth.roles.join(",");
    }

    const hasBody = !["GET", "HEAD"].includes(request.method);
    const upstreamResponse = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? JSON.stringify(request.body ?? {}) : undefined,
    });

    reply.code(upstreamResponse.status);
    const contentType = upstreamResponse.headers.get("content-type");
    if (contentType) reply.header("content-type", contentType);
    // Buffer, not .text() — .text() UTF-8-decodes the body, which silently
    // corrupts binary responses (PDFs). Buffer round-trips both binary and
    // text content correctly.
    reply.send(Buffer.from(await upstreamResponse.arrayBuffer()));
  };

  // find-my-way's wildcard (`prefix/*`) does not match the bare prefix with
  // no trailing segment, so both must be registered explicitly to cover
  // list/create calls like `GET /v1/quotes` or `POST /v1/customers`.
  app.all(opts.prefix, handler);
  app.all(`${opts.prefix}/*`, handler);
}
