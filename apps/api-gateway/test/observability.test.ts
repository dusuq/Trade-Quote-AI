import { describe, expect, it } from "vitest";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import jwt from "jsonwebtoken";
import { buildServer } from "../src/server.js";

const SECRET = "test-secret-at-least-32-bytes-long!!";

function sign(payload: object): string {
  return jwt.sign(payload, SECRET, { algorithm: "HS256" });
}

describe("observability (T309b)", () => {
  it("/metrics is public and exposes Prometheus exposition format", async () => {
    const app = buildServer({ jwtSecret: SECRET });
    await app.inject({ method: "GET", url: "/health" }); // generate a sample first
    const res = await app.inject({ method: "GET", url: "/metrics" });
    expect(res.statusCode).toBe(200);
    expect(res.headers["content-type"]).toContain("text/plain");
    expect(res.body).toContain("http_requests_total");
    await app.close();
  });

  it("excludes /metrics and /health from their own request-count series", async () => {
    const app = buildServer({ jwtSecret: SECRET });
    await app.inject({ method: "GET", url: "/health" });
    const res = await app.inject({ method: "GET", url: "/metrics" });
    expect(res.body).not.toMatch(/route="\/metrics"/);
    expect(res.body).not.toMatch(/route="\/health"/);
    await app.close();
  });

  it("boots and serves normally with SENTRY_DSN configured", async () => {
    const app = buildServer({
      jwtSecret: SECRET,
      sentryDsn: "https://public@sentry.example.com/1",
    });
    const res = await app.inject({ method: "GET", url: "/health" });
    expect(res.statusCode).toBe(200);
    await app.close();
  });

  it("injects a W3C traceparent header into the proxied request when OTEL is configured", async () => {
    let receivedTraceparent: string | null = null;
    const upstream = createServer((req, res) => {
      receivedTraceparent = (req.headers["traceparent"] as string | undefined) ?? null;
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
    });
    await new Promise<void>((resolve) => upstream.listen(0, resolve));
    const { port } = upstream.address() as AddressInfo;

    const app = buildServer({
      jwtSecret: SECRET,
      authServiceUrl: `http://127.0.0.1:${port}`,
      otelExporterOtlpEndpoint: "http://localhost:4318/v1/traces",
    });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/auth/me",
      headers: { authorization: `Bearer ${token}` },
    });
    expect(res.statusCode).toBe(200);
    // W3C traceparent: version-traceid(32 hex)-spanid(16 hex)-flags
    expect(receivedTraceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$/);

    upstream.close();
    await app.close();
  });

  it("does not inject a traceparent header when OTEL is not configured", async () => {
    let receivedTraceparent: string | null = null;
    const upstream = createServer((req, res) => {
      receivedTraceparent = (req.headers["traceparent"] as string | undefined) ?? null;
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
    });
    await new Promise<void>((resolve) => upstream.listen(0, resolve));
    const { port } = upstream.address() as AddressInfo;

    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: `http://127.0.0.1:${port}` });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/auth/me",
      headers: { authorization: `Bearer ${token}` },
    });
    expect(res.statusCode).toBe(200);
    expect(receivedTraceparent).toBeNull();

    upstream.close();
    await app.close();
  });
});
