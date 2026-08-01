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
            contentType: req.headers["content-type"] ?? null,
            bodyLength: body ? Buffer.byteLength(body) : 0,
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

  it("passes a real multipart/form-data body through unchanged (T201b voice-to-quote)", async () => {
    // Regression test for the Critical gateway finding: registerServiceProxy
    // used to unconditionally JSON.stringify the body and Fastify had no
    // content-type parser for multipart at all, so this 415'd before the
    // route handler ever ran. Build a real FormData (text field + Blob, like
    // an audio upload) via the platform Request/Response so the multipart
    // boundary and body bytes are generated exactly as a browser would.
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, aiServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });

    const form = new FormData();
    form.append("customer_id", "c1");
    form.append("audio", new Blob([Buffer.from([1, 2, 3, 4])], { type: "audio/webm" }), "clip.webm");
    const encoded = new Response(form);
    const contentType = encoded.headers.get("content-type")!;
    const bodyBuffer = Buffer.from(await encoded.arrayBuffer());

    const res = await app.inject({
      method: "POST",
      url: "/v1/ai/voice-to-quote",
      headers: { authorization: `Bearer ${token}`, "content-type": contentType },
      payload: bodyBuffer,
    });

    expect(res.statusCode).toBe(200);
    const json = res.json();
    expect(json.contentType).toContain("multipart/form-data");
    expect(json.contentType).toContain("boundary=");
    // Exact equality, not just >0 - JSON.stringify(someBuffer) also has a
    // non-zero length, so a regression back to the old JSON.stringify path
    // would satisfy a >0 check while still corrupting the body.
    expect(json.bodyLength).toBe(bodyBuffer.length);
    await app.close();
  });

  it("passes a multipart body larger than Fastify's 1 MiB parser default through to the upstream", async () => {
    // Regression test for the gateway's own bodyLimit: the catch-all buffer
    // parser inherits Fastify's default 1 MiB limit unless one is set
    // explicitly, which would 413 any real voice recording over about a
    // minute - well under ai-service's own 10 MiB max_audio_size_bytes -
    // silently, at the gateway, before ai-service's limit is ever checked.
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, aiServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });

    const form = new FormData();
    form.append("customer_id", "c1");
    form.append(
      "audio",
      new Blob([new Uint8Array(2 * 1024 * 1024)], { type: "audio/webm" }),
      "clip.webm",
    );
    const encoded = new Response(form);
    const contentType = encoded.headers.get("content-type")!;
    const bodyBuffer = Buffer.from(await encoded.arrayBuffer());

    const res = await app.inject({
      method: "POST",
      url: "/v1/ai/voice-to-quote",
      headers: { authorization: `Bearer ${token}`, "content-type": contentType },
      payload: bodyBuffer,
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().bodyLength).toBe(bodyBuffer.length);
    await app.close();
  });

  // ── T201c: the catch-all parser's bodyLimit is per-route, not global ──────
  //
  // The parser used to pin bodyLimit: 12 MiB on itself, which applied to
  // every route in the gateway. Authenticated routes were never exposed (auth
  // is an onRequest hook, so it 401s before the body is read), but the public
  // unauthenticated ones had no such gate and would buffer 12 MiB of
  // arbitrary bytes from an anonymous caller. These tests pin the split:
  // upload prefixes opt up, everything else sits at Fastify's 1 MiB default.

  /** A body over Fastify's 1 MiB default but under every raised limit here. */
  function oversizedBody() {
    return Buffer.alloc(2 * 1024 * 1024, 0x61);
  }

  it("caps a PUBLIC unauthenticated route at the 1 MiB default (T201c)", async () => {
    // The finding this task exists for. Before T201c this returned 200: the
    // parser's global 12 MiB let an anonymous caller push 2 MiB straight
    // through to esign-service. /v1/sign/* is public by design (the signer
    // has no account), so nothing else rejects it first.
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, esignServiceUrl: upstreamUrl });

    const res = await app.inject({
      method: "POST",
      url: "/v1/sign/abc123def456",
      headers: { "content-type": "application/octet-stream" },
      payload: oversizedBody(),
    });

    expect(res.statusCode).toBe(413);
    expect(res.json().code).toBe("FST_ERR_CTP_BODY_TOO_LARGE");
    await app.close();
  });

  it("still serves that same public route for a normally-sized body", async () => {
    // Guards the obvious over-correction: capping the limit must not break
    // the signing flow itself.
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, esignServiceUrl: upstreamUrl });

    const res = await app.inject({
      method: "POST",
      url: "/v1/sign/abc123def456",
      payload: { signature: "Jane Roe", consent: true },
    });

    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ method: "POST", url: "/v1/sign/abc123def456" });
    await app.close();
  });

  it("caps a non-upload authenticated prefix at the 1 MiB default (T201c)", async () => {
    // /v1/customers takes JSON only — it has no business buffering 2 MiB of
    // octet-stream. This is what proves the default actually dropped rather
    // than the 12 MiB simply moving somewhere else.
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });

    const res = await app.inject({
      method: "POST",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/octet-stream" },
      payload: oversizedBody(),
    });

    expect(res.statusCode).toBe(413);
    await app.close();
  });

  it("keeps the raised limit on /v1/pricebook for multipart CSV import (T201c)", async () => {
    // The regression T201c could easily have caused. POST /v1/pricebook/import
    // is a multipart CSV upload (pricebook-service `import_csv`) — a second
    // upload endpoint outside /v1/ai. Scoping the parser to the /v1/ai prefix,
    // as the T201b audit suggested, would have silently capped every catalog
    // import at 1 MiB.
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, pricebookServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });

    const csv = `sku,name,kind,unit,unit_cost_minor\n${"SKU-1,2in EMT conduit,material,ft,450\n".repeat(40_000)}`;
    const form = new FormData();
    form.append("file", new Blob([csv], { type: "text/csv" }), "pricebook.csv");
    const encoded = new Response(form);
    const bodyBuffer = Buffer.from(await encoded.arrayBuffer());
    expect(bodyBuffer.length).toBeGreaterThan(1024 * 1024); // the test is only meaningful over 1 MiB

    const res = await app.inject({
      method: "POST",
      url: "/v1/pricebook/import",
      headers: { authorization: `Bearer ${token}`, "content-type": encoded.headers.get("content-type")! },
      payload: bodyBuffer,
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().bodyLength).toBe(bodyBuffer.length);
    await app.close();
  });

  it("applies the raised limit to the bare prefix as well as the wildcard (T201c)", async () => {
    // registerServiceProxy mounts both `/v1/pricebook` and `/v1/pricebook/*`.
    // A bodyLimit passed to only one of them is the same half-registered-route
    // trap T203 fixed, and it would fail open on whichever was missed.
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, pricebookServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });

    const res = await app.inject({
      method: "POST",
      url: "/v1/pricebook",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/octet-stream" },
      payload: oversizedBody(),
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().bodyLength).toBe(2 * 1024 * 1024);
    await app.close();
  });

  it("still proxies a plain JSON POST unchanged after adding the catch-all content-type parser", async () => {
    // Guards against the catch-all buffer parser (added for the fix above)
    // breaking the existing JSON path - application/json must keep using
    // Fastify's built-in parser and get forwarded with the right
    // content-type. (This does not by itself distinguish a parsed object
    // from a byte-identical raw buffer; the multipart tests above are what
    // actually pin the Buffer-vs-JSON.stringify branch in proxy.ts.)
    const app = buildServer({ jwtSecret: SECRET, authServiceUrl: upstreamUrl, customerServiceUrl: upstreamUrl });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "POST",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${token}` },
      payload: { name: "Acme Co" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ method: "POST", url: "/v1/customers", contentType: "application/json" });
    await app.close();
  });

  it("requires a token for /v1/notifications and proxies it once authenticated", async () => {
    const app = buildServer({ jwtSecret: SECRET, notificationServiceUrl: upstreamUrl });
    expect(
      (await app.inject({ method: "POST", url: "/v1/notifications/send" })).statusCode,
    ).toBe(401);

    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "POST",
      url: "/v1/notifications/send",
      headers: { authorization: `Bearer ${token}` },
      payload: { channel: "email", recipient: "c@d.com", template_name: "quote_delivery" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ tenantHeader: "tenant-1", url: "/v1/notifications/send" });
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
