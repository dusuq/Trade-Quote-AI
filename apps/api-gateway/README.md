# API Gateway / BFF

- **Owner Agent:** Agent 1 — Opus 4.8
- **Bounded Context / Purpose:** Single secure entry point; routing, auth, rate limiting, aggregation
- **Status:** T103 implemented + verified (14/14 tests, typecheck + build clean).

## Responsibilities

- JWT verification on every request except a public allowlist (`/health`, `/v1/auth/register`, `/v1/auth/login`)
- Per-tenant rate limiting (falls back to per-IP for unauthenticated requests)
- Reverse-proxy routing to backend services, injecting trusted identity headers
  (`x-tenant-id`, `x-user-id`, `x-user-roles`, `x-request-id`) so downstream services never see the raw token
- Mobile/web aggregation point (BFF) — one secure entry, not one per service

## Architecture

```
src/
├── config.ts          zod-validated env config (JWT secret, upstream URLs, rate-limit settings)
├── types.ts            AuthClaims type + Fastify request augmentation
├── auth.ts              pure JWT verification core (framework-free, unit-tested directly)
├── plugins/
│   ├── auth.ts          Fastify onRequest hook: verifies bearer tokens, skips public paths
│   └── proxy.ts          generic reverse proxy: mounts `${prefix}/*` → upstream, forwards headers
├── routes/health.ts     liveness probe
└── server.ts             wires it together; buildServer(overrides?) for test injection
index.ts                 real entrypoint (reads env, listens)
```

Built on **Fastify** (Node/TypeScript). Auth is verified against the same HS256 secret as
[services/auth-service](../../services/auth-service) (T101) — same trust domain, no shared code
needed since JWTs are a portable contract.

## Adding a new backend service

Once a service ships (e.g. `customer-service`), add one line in `server.ts`:

```ts
registerServiceProxy(app, { prefix: "/v1/customers", upstream: cfg.customerServiceUrl });
```

and add `CUSTOMER_SERVICE_URL` to `config.ts`'s env schema.

## Known limitation (fast-follow)

A request rejected by the auth hook (missing/invalid token) short-circuits before the rate-limit
hook runs, so failed-auth attempts aren't currently rate-limited themselves. Low risk today (JWT
verification is local, no DB call) but a dedicated per-IP limit on `/v1/auth/login` and
`/v1/auth/register` is a reasonable follow-up once brute-force protection matters more.

## Develop

```bash
pnpm --filter @tradequote/api-gateway dev      # watch mode, port 8000
pnpm --filter @tradequote/api-gateway test     # 14 tests: JWT core + full server (auth-gating,
                                                # proxying, identity headers, rate limiting)
pnpm --filter @tradequote/api-gateway build    # compile to dist/
```

## Definition of Done

- ✅ JWT verification core is pure + unit-tested (8 cases: valid/expired/malformed/wrong-secret/etc.)
- ✅ Full server tested via Fastify `inject()` + a fake upstream (6 cases: health, proxy passthrough,
  401 on missing/invalid token, identity-header injection, rate-limit ceiling)
- ✅ Typecheck + build clean
- ⬜ Live integration against a running auth-service — natural once T002b's stack is up
- ⬜ Per-route stricter rate limiting on auth endpoints (documented fast-follow above)
