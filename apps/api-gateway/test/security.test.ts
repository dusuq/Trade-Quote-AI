/**
 * Security regression tests (T310 / M27).
 *
 * These are BEHAVIOURAL, not structural. An earlier draft of the T310 suite
 * asserted on the *source text* of proxy.ts and config.ts; mutation testing
 * showed it happily passed while the protections were commented out, because
 * the assertions matched the text inside the comment. Tests that grep source
 * are test theatre. These drive real requests through a real server and assert
 * on what a real upstream actually receives.
 *
 * The invariant under test: downstream services trust `x-tenant-id` blindly
 * (scripts/check_conventions.py forbids them from decoding JWTs). So the
 * gateway's header handling is the ONLY thing standing between a request and
 * another tenant's data.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import jwt from "jsonwebtoken";
import { buildServer } from "../src/server.js";
import { assertProductionSecrets, DEV_ONLY_JWT_SECRET, loadConfig } from "../src/config.js";

const SECRET = "test-secret-at-least-32-bytes-long!!";
const VICTIM_TENANT = "11111111-1111-1111-1111-111111111111";
const ATTACKER_TENANT = "22222222-2222-2222-2222-222222222222";

function sign(payload: object, secret = SECRET): string {
  return jwt.sign(payload, secret, { algorithm: "HS256" });
}

describe("security · gateway trust boundary", () => {
  let fakeUpstream: Server;
  let upstreamUrl: string;

  beforeAll(async () => {
    // Echoes back exactly what identity the upstream would act on.
    fakeUpstream = createServer((req, res) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(
        JSON.stringify({
          tenantHeader: req.headers["x-tenant-id"] ?? null,
          userHeader: req.headers["x-user-id"] ?? null,
          rolesHeader: req.headers["x-user-roles"] ?? null,
          forwardedFor: req.headers["x-forwarded-for"] ?? null,
        }),
      );
    });
    await new Promise<void>((resolve) => fakeUpstream.listen(0, resolve));
    const { port } = fakeUpstream.address() as AddressInfo;
    upstreamUrl = `http://127.0.0.1:${port}`;
  });

  afterAll(() => {
    fakeUpstream.close();
  });

  function testServer() {
    return buildServer({
      jwtSecret: SECRET,
      authServiceUrl: upstreamUrl,
      customerServiceUrl: upstreamUrl,
    });
  }

  it("an authenticated user cannot escalate to another tenant via x-tenant-id", async () => {
    // The core cross-tenant attack: a legitimate user of tenant A attaches a
    // header claiming tenant B. If it survives, they read B's customer list.
    const app = testServer();
    const token = sign({ sub: "user-1", tid: ATTACKER_TENANT, roles: ["owner"] });

    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: {
        authorization: `Bearer ${token}`,
        "x-tenant-id": VICTIM_TENANT,
      },
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().tenantHeader).toBe(ATTACKER_TENANT);
    expect(res.json().tenantHeader).not.toBe(VICTIM_TENANT);
    await app.close();
  });

  it("an authenticated user cannot escalate privileges via x-user-roles", async () => {
    // Roles drive authorization decisions downstream. A self-declared "admin"
    // header must never survive.
    const app = testServer();
    const token = sign({ sub: "user-1", tid: ATTACKER_TENANT, roles: ["viewer"] });

    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: {
        authorization: `Bearer ${token}`,
        "x-user-roles": "owner,admin,superuser",
        "x-user-id": "some-other-user",
      },
    });

    expect(res.json().rolesHeader).toBe("viewer");
    expect(res.json().userHeader).toBe("user-1");
    await app.close();
  });

  it("an anonymous caller cannot inject identity on a public route", async () => {
    // Public routes have request.auth === undefined, so nothing overwrites the
    // headers — the unconditional delete is the only protection here.
    const app = testServer();

    const res = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      headers: {
        "x-tenant-id": VICTIM_TENANT,
        "x-user-id": "admin",
        "x-user-roles": "owner",
      },
      payload: { email: "a@b.com", password: "x" },
    });

    expect(res.json().tenantHeader).toBeNull();
    expect(res.json().userHeader).toBeNull();
    expect(res.json().rolesHeader).toBeNull();
    await app.close();
  });

  it("a spoofed x-forwarded-for never reaches the e-signature audit trail", async () => {
    // esign-service records this as the signer's IP for legal evidence.
    const app = testServer();
    const token = sign({ sub: "user-1", tid: ATTACKER_TENANT, roles: ["owner"] });

    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: {
        authorization: `Bearer ${token}`,
        "x-forwarded-for": "203.0.113.66",
      },
    });

    expect(res.json().forwardedFor).not.toBe("203.0.113.66");
    await app.close();
  });
});

describe("security · token verification", () => {
  function testServer() {
    return buildServer({ jwtSecret: SECRET });
  }

  it('rejects an alg:"none" token', async () => {
    // The classic JWT bypass: an unsigned token asserting any identity.
    const app = testServer();
    const header = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString("base64url");
    const payload = Buffer.from(
      JSON.stringify({ sub: "attacker", tid: VICTIM_TENANT, roles: ["owner"] }),
    ).toString("base64url");

    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${header}.${payload}.` },
    });

    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("rejects a token signed with the wrong secret", async () => {
    const app = testServer();
    const forged = sign({ sub: "attacker", tid: VICTIM_TENANT, roles: ["owner"] }, "wrong-secret");

    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${forged}` },
    });

    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("rejects an expired token", async () => {
    const app = testServer();
    const expired = jwt.sign(
      {
        sub: "user-1",
        tid: ATTACKER_TENANT,
        roles: ["owner"],
        exp: Math.floor(Date.now() / 1000) - 60,
      },
      SECRET,
      { algorithm: "HS256" },
    );

    const res = await app.inject({
      method: "GET",
      url: "/v1/customers",
      headers: { authorization: `Bearer ${expired}` },
    });

    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("requires a token on a non-public route", async () => {
    const app = testServer();
    const res = await app.inject({ method: "GET", url: "/v1/customers" });
    expect(res.statusCode).toBe(401);
    await app.close();
  });
});

describe("security · fail-closed production secrets", () => {
  // The T310 headline finding. The gateway and auth-service both defaulted to
  // the SAME secret, committed in a public repo, with no environment guard
  // anywhere. Anyone could forge a token for any tenant with any role.

  it("refuses to start in production with the committed dev secret", () => {
    expect(() =>
      assertProductionSecrets({ nodeEnv: "production", jwtSecret: DEV_ONLY_JWT_SECRET }),
    ).toThrow(/JWT_SECRET is still the committed dev default/);
  });

  it("refuses staging too, not just production", () => {
    // Staging carries real-shaped data often enough to matter.
    expect(() =>
      assertProductionSecrets({ nodeEnv: "staging", jwtSecret: DEV_ONLY_JWT_SECRET }),
    ).toThrow();
  });

  it("refuses a too-short production secret", () => {
    expect(() => assertProductionSecrets({ nodeEnv: "production", jwtSecret: "short" })).toThrow(
      /at least 32/,
    );
  });

  it("accepts a strong secret in production", () => {
    expect(() =>
      assertProductionSecrets({
        nodeEnv: "production",
        jwtSecret: "a-genuinely-random-secret-of-sufficient-length-000",
      }),
    ).not.toThrow();
  });

  it("still allows the dev default locally so `docker compose up` works", () => {
    expect(() =>
      assertProductionSecrets({ nodeEnv: "local", jwtSecret: DEV_ONLY_JWT_SECRET }),
    ).not.toThrow();
  });

  it("loadConfig itself enforces the guard", () => {
    // Guards the wiring, not just the function: if loadConfig stops calling
    // assertProductionSecrets, the check exists but never runs.
    expect(() => loadConfig({ NODE_ENV: "production" } as NodeJS.ProcessEnv)).toThrow(
      /Refusing to start/,
    );
  });
});
