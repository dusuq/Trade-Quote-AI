import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import jwt from "jsonwebtoken";
import { buildServer } from "../src/server.js";

const SECRET = "test-secret-at-least-32-bytes-long!!";

function sign(payload: object): string {
  return jwt.sign(payload, SECRET, { algorithm: "HS256" });
}

describe("api-gateway", () => {
  let fakeUpstream: Server;
  let upstreamUrl: string;

  beforeAll(async () => {
    // Minimal fake auth-service: echoes back method/path/headers as JSON.
    fakeUpstream = createServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            method: req.method,
            url: req.url,
            tenantHeader: req.headers["x-tenant-id"] ?? null,
            userHeader: req.headers["x-user-id"] ?? null,
            forwardedFor: req.headers["x-forwarded-for"] ?? null,
            body: body || null,
          }),
        );
      });
    });
    await new Promise<void>((resolve) => fakeUpstream.listen(0, resolve));
    const { port } = fakeUpstream.address() as AddressInfo;
    upstreamUrl = `http://127.0.0.1:${port}`;
  });

  afterAll(() => {
    fakeUpstream.close();
  });

  function testServer() {
    return buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl });
  }

  it("GET /health is public and returns ok without a token", async () => {
    const app = testServer();
    const res = await app.inject({ method: "GET", url: "/health" });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ status: "ok", service: "api-gateway" });
    await app.close();
  });

  it("proxies POST /v1/auth/login through without requiring a token", async () => {
    const app = testServer();
    const res = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: { email: "a@b.com", password: "x" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ method: "POST", url: "/v1/auth/login" });
    await app.close();
  });

  it("rejects a protected route with no token", async () => {
    const app = testServer();
    const res = await app.inject({ method: "GET", url: "/v1/auth/me" });
    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("rejects a protected route with an invalid token", async () => {
    const app = testServer();
    const res = await app.inject({
      method: "GET",
      url: "/v1/auth/me",
      headers: { authorization: "Bearer garbage" },
    });
    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("allows a protected route with a valid token and injects identity headers upstream", async () => {
    const app = testServer();
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/auth/me",
      headers: { authorization: `Bearer ${token}` },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({
      method: "GET",
      url: "/v1/auth/me",
      tenantHeader: "tenant-1",
      userHeader: "user-1",
    });
    await app.close();
  });

  it("enforces the rate limit ceiling", async () => {
    const app = testServer();
    const limited = buildServer({
      jwtSecret: SECRET,
      authServiceUrl: upstreamUrl,
      rateLimitMax: 2,
      rateLimitWindowMs: 60_000,
    });
    const first = await limited.inject({ method: "GET", url: "/health" });
    const second = await limited.inject({ method: "GET", url: "/health" });
    const third = await limited.inject({ method: "GET", url: "/health" });
    expect(first.statusCode).toBe(200);
    expect(second.statusCode).toBe(200);
    expect(third.statusCode).toBe(429);
    await limited.close();
    await app.close();
  });

  it("allows GET /v1/proposals/<uuid>/view with no token", async () => {
    const app = testServer();
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/11111111-1111-1111-1111-111111111111/view",
    });
    // The fake upstream (auth-service) doesn't implement this path, but the
    // point is it's not rejected at the gateway with 401 before even proxying.
    expect(res.statusCode).not.toBe(401);
    await app.close();
  });

  it("strips a client-supplied x-tenant-id on the public /view route with no token", async () => {
    const app = buildServer({
      jwtSecret: SECRET,
      authServiceUrl: upstreamUrl,
      proposalServiceUrl: upstreamUrl,
    });
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/11111111-1111-1111-1111-111111111111/view",
      headers: { "x-tenant-id": "attacker-supplied-value" },
    });
    expect(res.statusCode).not.toBe(401);
    expect(res.json()).toMatchObject({ tenantHeader: null });
    await app.close();
  });

  it("still rejects a non-view proposals route with no token", async () => {
    const app = testServer();
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/11111111-1111-1111-1111-111111111111",
    });
    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("reaches the upstream for GET /v1/customers with no trailing slash (bare prefix)", async () => {
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}` },
    });
    expect(res.statusCode).not.toBe(404);
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ method: "GET", url: "/v1/customers" });
    await app.close();
  });

  it("reaches the upstream for POST /v1/customers with no trailing slash (bare prefix)", async () => {
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "POST",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}` },
      payload: { name: "Acme Co" },
    });
    expect(res.statusCode).not.toBe(404);
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ method: "POST", url: "/v1/customers" });
    await app.close();
  });

  it("passes binary response bytes through unchanged", async () => {
    const binaryUpstream = createServer((req, res) => {
      // Bytes that are NOT valid UTF-8 on their own (a lone continuation byte) —
      // decoding+re-encoding as text would corrupt this, proving the fix works.
      const raw = Buffer.from([0x25, 0x50, 0x44, 0x46, 0xff, 0xfe, 0x00, 0x01]);
      res.writeHead(200, { "content-type": "application/pdf" });
      res.end(raw);
    });
    await new Promise<void>((resolve) => binaryUpstream.listen(0, resolve));
    const { port } = binaryUpstream.address() as AddressInfo;

    const app = buildServer({
      jwtSecret: SECRET,
      authServiceUrl: upstreamUrl,
      proposalServiceUrl: `http://127.0.0.1:${port}`,
    });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/abc/pdf",
      headers: { authorization: `Bearer ${token}` },
    });
    const expected = Buffer.from([0x25, 0x50, 0x44, 0x46, 0xff, 0xfe, 0x00, 0x01]);
    expect(Buffer.compare(res.rawPayload, expected)).toBe(0);

    binaryUpstream.close();
    await app.close();
  });

  // ── M10 / T204: public signing links + trustworthy client IP ──

  it("proxies GET /v1/sign/{token} publicly, with no token required", async () => {
    const app = buildServer({ jwtSecret: SECRET, esignServiceUrl: upstreamUrl });
    const res = await app.inject({ method: "GET", url: "/v1/sign/abc123_token-XYZ" });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ method: "GET", url: "/v1/sign/abc123_token-XYZ" });
    await app.close();
  });

  it("proxies POST /v1/sign/{token}/decline publicly", async () => {
    const app = buildServer({ jwtSecret: SECRET, esignServiceUrl: upstreamUrl });
    const res = await app.inject({
      method: "POST",
      url: "/v1/sign/abc123_token-XYZ/decline",
      payload: { reason: "no thanks" },
    });
    expect(res.statusCode).toBe(200);
    await app.close();
  });

  it("does NOT make the authenticated /v1/signature-requests surface public", async () => {
    // Guards the public-route regex against being widened into an auth bypass.
    const app = buildServer({ jwtSecret: SECRET, esignServiceUrl: upstreamUrl });
    const res = await app.inject({ method: "GET", url: "/v1/signature-requests" });
    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("path traversal under /v1/sign cannot reach the authenticated collection", async () => {
    const app = buildServer({ jwtSecret: SECRET, esignServiceUrl: upstreamUrl });
    const res = await app.inject({ method: "GET", url: "/v1/sign/tok/../signature-requests" });
    // The URL normalizes to /v1/sign/signature-requests before routing, so it
    // stays inside the public signing route with "signature-requests" as a
    // (nonsense) token — which the real esign-service 404s on lookup. What
    // matters is that it never lands on the authenticated collection endpoint.
    expect(res.json().url).toBe("/v1/sign/signature-requests");
    expect(res.json().url).not.toBe("/v1/signature-requests");
    await app.close();
  });

  it("requires a token for /v1/ai and proxies it once authenticated", async () => {
    const app = buildServer({ jwtSecret: SECRET, aiServiceUrl: upstreamUrl });
    expect((await app.inject({ method: "POST", url: "/v1/ai/text-to-quote" })).statusCode).toBe(401);

    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "POST",
      url: "/v1/ai/text-to-quote",
      headers: { authorization: `Bearer ${token}` },
      payload: { text: "replace the panel", customer_id: "c1" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ tenantHeader: "tenant-1", url: "/v1/ai/text-to-quote" });
    await app.close();
  });

  it("overwrites a client-supplied x-forwarded-for with the real peer address", async () => {
    // esign-service writes this into a legal audit trail as the signer's IP,
    // so a caller must not be able to choose what gets recorded there.
    const app = buildServer({ jwtSecret: SECRET, esignServiceUrl: upstreamUrl });
    const res = await app.inject({
      method: "POST",
      url: "/v1/sign/abc123_token-XYZ",
      headers: { "x-forwarded-for": "203.0.113.66" },
      payload: { typed_name: "Mallory" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().forwardedFor).not.toBe("203.0.113.66");
    await app.close();
  });
});
