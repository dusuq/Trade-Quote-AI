/**
 * T310b — security observability at the gateway.
 *
 * Behavioural, following the lesson recorded in docs/13-SECURITY-REVIEW-OWASP.md:
 * the first version of the T310 suite asserted on source text and 3 of 4
 * sabotages passed undetected. So nothing here greps a file — every case
 * drives a real request through a real server and then reads the real
 * `/metrics` exposition, which is the same thing Prometheus would scrape.
 * Delete the `recordIdentityHeaderSpoofing` call from proxy.ts and these fail.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import jwt from "jsonwebtoken";
import { buildServer } from "../src/server.js";
import { resetSecurityMetricsForTests } from "../src/plugins/security-metrics.js";

const SECRET = "test-secret-at-least-32-bytes-long!!";
const OTHER_SECRET = "a-completely-different-32-byte-secret";

function sign(payload: object, secret = SECRET, options: jwt.SignOptions = {}): string {
  return jwt.sign(payload, secret, { algorithm: "HS256", ...options });
}

/** Minimal upstream that 200s everything — these tests care about the gateway. */
function startUpstream(): Promise<{ server: Server; url: string }> {
  return new Promise((resolve) => {
    const server = createServer((_req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
    });
    server.listen(0, () => {
      const { port } = server.address() as AddressInfo;
      resolve({ server, url: `http://127.0.0.1:${port}` });
    });
  });
}

/**
 * Read the value of one Prometheus counter sample out of the real exposition
 * text, matching on the labels given. Returns 0 when no such series exists —
 * an absent series and a zero series mean the same thing to an alert rule.
 */
function counterValue(body: string, metric: string, labels: Record<string, string>): number {
  const wanted = Object.entries(labels);
  for (const line of body.split("\n")) {
    if (!line.startsWith(`${metric}{`)) continue;
    const labelBlob = line.slice(line.indexOf("{") + 1, line.lastIndexOf("}"));
    const matches = wanted.every(([k, v]) => labelBlob.includes(`${k}="${v}"`));
    if (matches) return Number(line.slice(line.lastIndexOf("}") + 1).trim());
  }
  return 0;
}

let upstream: Server;
let upstreamUrl: string;

beforeEach(async () => {
  resetSecurityMetricsForTests();
  const started = await startUpstream();
  upstream = started.server;
  upstreamUrl = started.url;
});

afterEach(() => {
  upstream.close();
});

describe("auth-failure metrics (T310b)", () => {
  it("counts a request with no bearer token as missing_token", async () => {
    const app = buildServer({ jwtSecret: SECRET });
    const res = await app.inject({ method: "GET", url: "/v1/customers" });
    expect(res.statusCode).toBe(401);

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(
      counterValue(metrics.body, "auth_failures_total", {
        reason: "missing_token",
        route: "/v1/customers",
      }),
    ).toBe(1);
    await app.close();
  });

  it("distinguishes a forged signature from an expired token", async () => {
    const app = buildServer({ jwtSecret: SECRET });

    // Signed with the wrong key — nobody does this by accident.
    await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${sign({ sub: "u", tid: "t", roles: [] }, OTHER_SECRET)}` },
    });
    // Correctly signed, simply stale — ordinary traffic.
    await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: {
        authorization: `Bearer ${sign({ sub: "u", tid: "t", roles: [] }, SECRET, { expiresIn: -60 })}`,
      },
    });

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(counterValue(metrics.body, "auth_failures_total", { reason: "invalid_signature" })).toBe(
      1,
    );
    expect(counterValue(metrics.body, "auth_failures_total", { reason: "expired_token" })).toBe(1);
    await app.close();
  });

  it("counts alg:none forgeries under the forgery reasons, not a generic bucket", async () => {
    const app = buildServer({ jwtSecret: SECRET });
    const header = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString("base64url");
    const payload = Buffer.from(
      JSON.stringify({ sub: "u", tid: "victim", roles: ["owner"] }),
    ).toString("base64url");

    // The textbook version: empty signature segment.
    const empty = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${header}.${payload}.` },
    });
    expect(empty.statusCode).toBe(401);
    // The same forgery with junk in the signature segment, which jsonwebtoken
    // reports differently — both must land on a forgery reason, because the
    // alert rule keys off exactly those two labels.
    const junk = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${header}.${payload}.AAAA` },
    });
    expect(junk.statusCode).toBe(401);

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(counterValue(metrics.body, "auth_failures_total", { reason: "invalid_signature" })).toBe(
      1,
    );
    expect(counterValue(metrics.body, "auth_failures_total", { reason: "invalid_algorithm" })).toBe(
      1,
    );
    expect(counterValue(metrics.body, "auth_failures_total", { reason: "invalid_token" })).toBe(0);
    await app.close();
  });

  it("counts garbage in the Authorization header as malformed_token", async () => {
    const app = buildServer({ jwtSecret: SECRET });
    await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: "Bearer not-a-jwt-at-all" },
    });

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(counterValue(metrics.body, "auth_failures_total", { reason: "malformed_token" })).toBe(
      1,
    );
    await app.close();
  });

  it("labels the route pattern, never the concrete URL with its ids", async () => {
    const app = buildServer({ jwtSecret: SECRET });
    await app.inject({ method: "GET", url: "/v1/customers/11111111-1111-1111-1111-111111111111" });
    await app.inject({ method: "GET", url: "/v1/customers/22222222-2222-2222-2222-222222222222" });

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    // Both requests land on the same series — otherwise an unauthenticated
    // caller could mint unbounded Prometheus cardinality by varying the id.
    expect(
      counterValue(metrics.body, "auth_failures_total", {
        reason: "missing_token",
        route: "/v1/customers/*",
      }),
    ).toBe(2);
    expect(metrics.body).not.toContain("11111111-1111-1111-1111-111111111111");
    await app.close();
  });

  it("does not count a successful request", async () => {
    const app = buildServer({ jwtSecret: SECRET, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "u", tid: "tenant-a", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}` },
    });
    expect(res.statusCode).toBe(200);

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(counterValue(metrics.body, "auth_failures_total", { route: "/v1/customers" })).toBe(0);
    await app.close();
  });
});

describe("cross-tenant-attempt metrics (T310b)", () => {
  it("counts an authenticated caller spoofing another tenant's x-tenant-id", async () => {
    const app = buildServer({ jwtSecret: SECRET, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "u", tid: "tenant-a", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}`, "x-tenant-id": "tenant-b" },
    });
    // Still served — the request is legitimate, only the spoofed header is
    // dropped. The point of T310b is that the drop is now *visible*.
    expect(res.statusCode).toBe(200);

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(
      counterValue(metrics.body, "cross_tenant_attempts_total", {
        header: "x-tenant-id",
        route: "/v1/customers",
        authenticated: "true",
      }),
    ).toBe(1);
    await app.close();
  });

  it("counts a role-escalation attempt via x-user-roles", async () => {
    const app = buildServer({ jwtSecret: SECRET, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "u", tid: "tenant-a", roles: ["viewer"] });
    await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}`, "x-user-roles": "owner" },
    });

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(
      counterValue(metrics.body, "cross_tenant_attempts_total", { header: "x-user-roles" }),
    ).toBe(1);
    await app.close();
  });

  it("counts identity headers injected on a public, unauthenticated route", async () => {
    const app = buildServer({ jwtSecret: SECRET, proposalServiceUrl: upstreamUrl });
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/11111111-1111-1111-1111-111111111111/view",
      headers: { "x-tenant-id": "tenant-b", "x-user-id": "someone" },
    });
    expect(res.statusCode).toBe(200);

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    // Nobody has claims here, so *any* identity header is injected — both are
    // counted, and `authenticated="false"` marks them as anonymous probing.
    expect(
      counterValue(metrics.body, "cross_tenant_attempts_total", {
        header: "x-tenant-id",
        authenticated: "false",
      }),
    ).toBe(1);
    expect(
      counterValue(metrics.body, "cross_tenant_attempts_total", {
        header: "x-user-id",
        authenticated: "false",
      }),
    ).toBe(1);
    await app.close();
  });

  it("does not count a client that echoes back its own verified identity", async () => {
    const app = buildServer({ jwtSecret: SECRET, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-a", roles: ["owner", "admin"] });
    await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: {
        authorization: `Bearer ${token}`,
        "x-tenant-id": "tenant-a",
        "x-user-id": "user-1",
        // Same roles, different order — the same authorization, so paging a
        // human for it would be a false positive.
        "x-user-roles": "admin,owner",
      },
    });

    const metrics = await app.inject({ method: "GET", url: "/metrics" });
    expect(
      counterValue(metrics.body, "cross_tenant_attempts_total", { route: "/v1/customers" }),
    ).toBe(0);
    await app.close();
  });

  it("still strips the spoofed headers it counts", async () => {
    // The counter must be additional to the defence, never a replacement for
    // it. This re-asserts the T310 invariant through the new code path.
    let receivedTenant: string | undefined;
    const echo = createServer((req, res) => {
      receivedTenant = req.headers["x-tenant-id"] as string | undefined;
      res.writeHead(200, { "content-type": "application/json" });
      res.end("{}");
    });
    await new Promise<void>((resolve) => echo.listen(0, resolve));
    const { port } = echo.address() as AddressInfo;

    const app = buildServer({
      jwtSecret: SECRET,
      customerServiceUrl: `http://127.0.0.1:${port}`,
    });
    const token = sign({ sub: "u", tid: "tenant-a", roles: ["owner"] });
    await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}`, "x-tenant-id": "tenant-b" },
    });

    expect(receivedTenant).toBe("tenant-a");
    echo.close();
    await app.close();
  });
});
