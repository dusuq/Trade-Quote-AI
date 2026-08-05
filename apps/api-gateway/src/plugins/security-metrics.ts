/**
 * Security observability at the gateway (T310b / M27 — OWASP A09).
 *
 * T309b answered "is the traffic healthy". This answers "is someone attacking
 * it". The gateway is the only place in the platform that sees both the raw,
 * untrusted request *and* the verified claims, so it is the only place these
 * two signals can be produced at all:
 *
 *   1. `auth_failures_total` — why authentication was refused, split finely
 *      enough that a forgery attempt (wrong signature / wrong algorithm) is
 *      distinguishable from ordinary expiry. See AuthFailureReason in auth.ts.
 *   2. `cross_tenant_attempts_total` — a client that supplied an identity
 *      header (`x-tenant-id` / `x-user-id` / `x-user-roles`) contradicting its
 *      verified claims, or supplied one at all on an unauthenticated route.
 *
 * (2) is the load-bearing one. proxy.ts has always *stripped* those headers
 * before repopulating them from verified claims — the isolation was already
 * correct — but it stripped them **silently**. A caller could probe every
 * tenant id in the platform, be correctly refused every time, and leave no
 * trace anywhere. The defence was working and unobservable, which is the
 * exact shape of the A09 finding.
 *
 * These counters register into prom-client's default registry, which is what
 * plugins/observability.ts serves at `/metrics` — no separate exposition path.
 */
import type { FastifyRequest } from "fastify";
import client from "prom-client";
import type { AuthFailureReason } from "../auth.js";
import { routeLabel } from "./observability.js";

/**
 * Module-level, exactly like observability.ts's counters: prom-client throws
 * on a duplicate metric name in the same registry, and buildServer() runs
 * once per test in this suite.
 */
const authFailuresTotal = new client.Counter({
  name: "auth_failures_total",
  help: "Requests refused by the gateway's JWT check, by reason and route.",
  labelNames: ["reason", "route"],
});

const crossTenantAttemptsTotal = new client.Counter({
  name: "cross_tenant_attempts_total",
  help:
    "Requests that supplied a trusted identity header contradicting the verified " +
    "token claims (or supplied one at all on a public route), by header and route.",
  labelNames: ["header", "route", "authenticated"],
});

/** The headers downstream services trust unconditionally. */
export const IDENTITY_HEADERS = ["x-tenant-id", "x-user-id", "x-user-roles"] as const;
export type IdentityHeader = (typeof IDENTITY_HEADERS)[number];

/**
 * Cap on how much attacker-controlled header text reaches the log line. The
 * value is recorded because it is genuinely useful during an investigation
 * ("which tenant were they probing"), but an unbounded header is a log-volume
 * amplifier, and Loki bills by ingested bytes.
 */
const MAX_LOGGED_VALUE = 200;

function truncate(value: string): string {
  return value.length <= MAX_LOGGED_VALUE ? value : `${value.slice(0, MAX_LOGGED_VALUE)}…`;
}

export function recordAuthFailure(request: FastifyRequest, reason: AuthFailureReason): void {
  const route = routeLabel(request);
  authFailuresTotal.inc({ reason, route });

  // Structured, so promtail ships it to Loki with the fields intact and an
  // incident responder can group by reason/ip without regexing free text.
  // `warn`, not `error`: an expired token is normal traffic, and burying a
  // real forgery attempt under a flood of self-inflicted errors is how the
  // signal gets ignored. The alert rules do the severity judgement, not the
  // log level (see infra/monitoring/prometheus/rules/security-metrics.yml).
  request.log.warn(
    { event: "security.auth_failure", reason, route, ip: request.ip, method: request.method },
    "authentication refused",
  );
}

/**
 * Compare a supplied identity header against the verified claims.
 *
 * Returns true when the header is a genuine contradiction. An *exact* match is
 * not counted: an over-eager SDK echoing a tenant's own id back is not an
 * attack, and counting it would bury the real signal in false positives. The
 * header is still stripped and re-derived either way — this function only
 * decides whether anyone should be told about it.
 */
function contradictsClaims(
  header: IdentityHeader,
  supplied: string,
  request: FastifyRequest,
): boolean {
  const auth = request.auth;
  if (!auth) return true; // public route: no claims exist, so any identity header is injected

  switch (header) {
    case "x-tenant-id":
      return supplied !== auth.tid;
    case "x-user-id":
      return supplied !== auth.sub;
    case "x-user-roles": {
      // Set comparison, not string equality: the same roles in a different
      // order is the same authorization, and paging someone for it would be
      // a false positive. A *different* role set is privilege escalation.
      const claimed = new Set(auth.roles);
      const asked = supplied
        .split(",")
        .map((r) => r.trim())
        .filter(Boolean);
      return asked.length !== claimed.size || asked.some((r) => !claimed.has(r));
    }
  }
}

/**
 * Count and log every client-supplied identity header that contradicts the
 * verified claims.
 *
 * MUST be called by proxy.ts *before* the headers are deleted — after the
 * strip there is nothing left to observe. That ordering is locked by
 * tests/security/test_security_invariants.py.
 */
export function recordIdentityHeaderSpoofing(request: FastifyRequest): void {
  const route = routeLabel(request);
  const authenticated = request.auth ? "true" : "false";

  for (const header of IDENTITY_HEADERS) {
    const supplied = request.headers[header];
    if (typeof supplied !== "string" || supplied.trim() === "") continue;
    if (!contradictsClaims(header, supplied, request)) continue;

    crossTenantAttemptsTotal.inc({ header, route, authenticated });
    request.log.warn(
      {
        event: "security.cross_tenant_attempt",
        header,
        route,
        method: request.method,
        ip: request.ip,
        supplied: truncate(supplied),
        // The identity the request actually has. Undefined on public routes,
        // which is itself the interesting case — nobody should be sending
        // identity headers to an unauthenticated endpoint.
        verifiedTenantId: request.auth?.tid,
        verifiedUserId: request.auth?.sub,
      },
      "client-supplied identity header rejected",
    );
  }
}

/** Test seam: reset both counters between cases without touching the registry. */
export function resetSecurityMetricsForTests(): void {
  authFailuresTotal.reset();
  crossTenantAttemptsTotal.reset();
}
