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
});
