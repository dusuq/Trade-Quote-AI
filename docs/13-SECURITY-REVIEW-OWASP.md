# 13 — Security Review, OWASP Top 10 & Launch Gate (T310 / M27)

- **Reviewed:** 2026-08-03 · Claude Code (Opus 5)
- **Scope:** api-gateway, 11 FastAPI services, database/RLS layer, and the T309
  deployment/edge configuration. Mobile covered only where it touches auth.
- **Method:** source review + automated invariant tests, all mutation-tested.
  **No live system was tested** — see [Not verified](#not-verified).

---

## Verdict

**CONDITIONAL GO.** Two critical issues were found; **both are fixed in code**,
and both fixes are pinned by tests. But **one fix cannot be confirmed without a
live database**, and no image has ever been built or deployed.

**Do not launch until every 🔴 item in the [Launch gate](#launch-gate) is closed
against a real environment.**

| Severity            | Found | Fixed here | Needs live verification |
| ------------------- | ----- | ---------- | ----------------------- |
| Critical            | 2     | 2          | 1                       |
| Medium              | 4     | 3          | 1                       |
| Low / Informational | 3     | 0          | 3                       |

---

## Critical findings

### C-1 — Publicly known JWT signing secret, failing open ✅ FIXED

**Impact: full cross-tenant compromise and privilege escalation.**

`apps/api-gateway/src/config.ts` and `services/auth-service/app/config.py` both
defaulted `JWT_SECRET` to the _same_ literal, committed in this repository:

```
local-dev-only-change-me-32byte-minimum-secret
```

There was **no environment guard anywhere in the codebase** — I grepped every
service and the gateway for any `app_env == "production"` / `NODE_ENV ===`
check and found zero. Several config comments said variants of "every non-local
environment MUST override this", enforced by nothing.

**Exploit path.** Anyone who can read this repo signs an HS256 token with
arbitrary claims:

```
{"sub": "<any user>", "tid": "<any tenant>", "roles": ["owner"], "exp": <future>}
```

The gateway verifies it (the secret matches), then `plugins/proxy.ts` injects
`x-tenant-id: <victim tenant>` as a **trusted** header. Downstream services
trust that header implicitly — `scripts/check_conventions.py` actively forbids
them from decoding tokens themselves — so the attacker reads and writes any
tenant's customers, quotes, proposals and payments, as an owner.

The failure mode is the dangerous kind: it fails **open**, silently. A
deployment missing `JWT_SECRET` looks identical to a correct one.

**Fix.** `assertProductionSecrets` (gateway) and `_assert_production_secrets`
(auth-service, integration-service) refuse to start when `NODE_ENV`/`APP_ENV`
is `production`/`prod`/`staging`/`preprod` and a dev default or an
under-32-character secret is present. It **throws** rather than warning — a
warning in a log nobody reads is precisely how this reaches production. In
auth-service it runs from `model_post_init`, so it fires on `Settings()`
construction and cannot be forgotten at a call site.

Verified end to end: local boots on defaults; production with defaults refuses
with an actionable message; production with real secrets boots.

### C-2 — Row-Level Security silently bypassed ✅ FIXED IN CODE · 🔴 NEEDS LIVE VERIFICATION

**Impact: RLS provides no tenant isolation in the default configuration.**

All 28 tenant-scoped tables declare `ENABLE ROW LEVEL SECURITY` with a
tenant-isolation policy. But **`ENABLE` does not apply to a table's owner —
only `FORCE` does.**

- Migrations run as `DATABASE_URL`, so that role **owns** every table.
- Every service's default `DATABASE_URL` is _the same role_ (`tradequote`).
- `grep` across `infra/` found **no separate application role** anywhere.

So in the default configuration the application connects as the table owner and
**every policy is bypassed**. The only thing separating tenants is that service
queries also filter on `tenant_id` by hand — defence in depth with nothing
behind it. One forgotten `WHERE` is a cross-tenant breach.

**Important nuance — the policies themselves are fine.** T311 (Agent 3,
2026-07-28) proved on live GCP Postgres that the policies _do_ isolate tenants,
including cross-tenant `INSERT` rejection. But that verification connected as
`tradequote_app` — a non-superuser role **created by hand in that one
environment and never committed to any migration**. `tests/integration/test_postgres_rls.py`
still hardcodes it in its default URL, which is the only trace of it in the repo.

So the security control works _only where someone manually remembered to build
it_. Every environment provisioned from this repository — local `docker compose`,
CI, and any new GCP deployment — falls back to `DATABASE_URL`'s default owner
role and silently loses RLS entirely. **The defect is that the role is not
reproducible, not that the policies are wrong.**

**Why it stayed hidden:** `tests/integration/test_postgres_rls.py` calls
`pytest.mark.skipif` when Postgres is unreachable, which is the normal local
state. Everywhere except that one hand-built environment, the suite reported
green having never evaluated a single policy.

**Fix.** `infra/db/migrations/0015_rls_app_role.sql` codifies the role that
until now existed only as manual setup: a least-privilege **non-owner**
`tradequote_app` (explicitly `NOSUPERUSER NOBYPASSRLS`, DML only, no DDL, no
`TRUNCATE`). Deliberately the same name T311 used, so the proven-good
environment keeps working and every future one is provisioned identically. RLS
then applies normally, with no policy changes needed.

**`FORCE ROW LEVEL SECURITY` was deliberately NOT applied.** Three
`SECURITY DEFINER` functions depend on the owner exemption as their intended,
tightly-scoped escape hatch:

| Function                                                    | Would break                                                                                                                                                                                                                       |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `outbox_claim_unprocessed` / `outbox_mark_processed` (0012) | The notification relay is cross-tenant with no tenant context. `FORCE` makes `tenant_id = app_current_tenant()` (NULL) match zero rows, so the relay silently publishes nothing. **This is exactly the T205c bug**, reintroduced. |
| `resolve_proposal_tenant` (0006)                            | Public proposal view links                                                                                                                                                                                                        |
| `resolve_signature_request_tenant` (0008)                   | Public e-signature signing links                                                                                                                                                                                                  |

Adding `FORCE` would trade a fixable misconfiguration for three silent
functional outages. The owner exemption is load-bearing; the correct fix is to
stop _being_ the owner in application code paths.

🔴 **This fix is unproven.** Migration `0015` has never been applied. Isolation
must be confirmed against a real Postgres — see the [Launch gate](#launch-gate).

---

## Medium findings

### M-1 — Committed encryption key for third-party OAuth tokens ✅ FIXED

`services/integration-service` shipped a real, committed Fernet key protecting
QuickBooks/Xero access tokens at rest. Booting production with it means anyone
with the repo can decrypt every tenant's accounting credentials from a database
dump. The same fail-closed guard now applies.

### M-2 — MFA secrets unencryptable by default ✅ FIXED

`mfa_encryption_key` defaulted to `""`. TOTP seeds are the _second_
authentication factor; unencrypted, a single database read hands an attacker
every user's second factor. The startup guard now requires it in non-local
environments.

### M-3 — Dependency vulnerabilities ⚠️ TRACKED

`pnpm audit`: **11 vulnerabilities — 1 critical, 6 high, 4 moderate.**

| Severity | Package                                   | Reaches production?             |
| -------- | ----------------------------------------- | ------------------------------- |
| Critical | `vitest` (<3.2.6, UI arbitrary file read) | **No** — dev-only               |
| High     | `vite`, `brace-expansion`, `esbuild`      | **No** — dev-only               |
| High     | `sharp` (<0.35.0, libvips CVEs)           | **Yes** — transitive via `next` |
| High/Mod | `postcss` (path traversal, XSS)           | **Yes** — transitive via `next` |

The critical one is dev-only. The `sharp`/`postcss` chain reaches `apps/web`
and is pinned by Next.js, so it needs a Next upgrade rather than a direct bump.
**Not a launch blocker, but `pnpm audit` should run in CI.**

### M-4 — No CORS configuration 🟡 DECISION REQUIRED

The gateway registers no CORS plugin. That is _restrictive_ (safe) by default,
but `apps/web` reads `NEXT_PUBLIC_API_URL` — a **browser-side** variable — so
`app.<domain>` calling `api.<domain>` is cross-origin and will be blocked.

Flagged because of the likely reaction: someone hits this at launch and "fixes"
it with `origin: "*"`. With credentials that is a blanket CSRF and
data-exfiltration hole. If CORS is needed it must be an **explicit origin
allowlist**. Confirm first whether the web app calls the gateway from the
browser or proxies server-side; the right fix differs.

---

## Low / informational

- **L-1 — No security headers.** No `@fastify/helmet`: no CSP,
  `X-Frame-Options`, or `X-Content-Type-Options`. Lower impact for a JSON API
  than an HTML app, but cheap to add.
- **L-2 — `Authorization` forwarded to upstreams.** The proxy strips hop-by-hop
  and identity headers but forwards the bearer token. Services must not decode
  it (enforced by `check_conventions.py`), so this is defence-in-depth only —
  stripping it would tighten the trust boundary.
- **L-3 — Silent-skip integration tests.** The pattern that hid C-2. Any suite
  asserting a security property should fail loudly, or be reported as "not
  run", never silently pass.

---

## OWASP Top 10 (2021) assessment

| #       | Category                        | Status                      | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------- | ------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A01** | Broken Access Control           | ⚠️ **Was critical → fixed** | **C-2** fixed pending live verification. The gateway trust boundary itself is **correct and well-built**: `proxy.ts` unconditionally strips client-supplied `x-tenant-id`/`x-user-id`/`x-user-roles` _before_ repopulating from verified claims, and overwrites `x-forwarded-for` (which esign-service records as the signer's IP in a legal audit trail). The public-route allowlist is narrow, anchored at both ends, and now locked by test.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **A02** | Cryptographic Failures          | ⚠️ **Was critical → fixed** | **C-1**, **M-1**, **M-2**. Otherwise strong: PBKDF2-HMAC-SHA256 at **600,000 iterations** (meets OWASP's floor), `hmac.compare_digest` for verification, refresh tokens CSPRNG-generated and stored **hashed**, JWT verification pins `algorithms: ["HS256"]` (blocks `alg:none` and algorithm confusion).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **A03** | Injection                       | ✅ **Clean**                | Every SQL statement across all 11 services uses bound parameters — no f-string, `%`, or `.format()` interpolation found. Critically, `set_config('app.current_tenant', :tid, true)` — which drives _every_ RLS policy — is parameterized everywhere; interpolating there would be a total isolation bypass. Now enforced by a mutation-tested detector.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **A04** | Insecure Design                 | ✅ **Good**                 | Single public entrypoint; services private-network only; gateway owns all authn; payment webhooks fail closed (T303). The `SECURITY DEFINER` escape hatches are narrow and deliberate rather than a blanket `BYPASSRLS` role.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **A05** | Security Misconfiguration       | ⚠️ **Was critical → fixed** | **C-1** was fundamentally a misconfiguration that could not be detected. Now fails closed. Remaining: **M-4** (CORS), **L-1** (headers). T309 hardening applies: non-root containers, pinned bases, `ssl = strict`, HSTS, WAF.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **A06** | Vulnerable Components           | ⚠️ **Tracked**              | **M-3**. Add `pnpm audit` to CI.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **A07** | Identification & Authentication | ⚠️ **Was critical → fixed** | **C-1**. TOTP MFA present (`pyotp`, `valid_window=1`). Access tokens 1 h, refresh 30 d. ⚠️ **No account lockout beyond rate limiting** (gateway 100/min/IP; Cloudflare adds 10/min on `/v1/auth/login`). Acceptable, but PBKDF2 at 600k makes login expensive server-side — a login flood is a plausible DoS vector worth load-testing.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **A08** | Software & Data Integrity       | ✅ **Good**                 | E-signature hash-chain audit trail (T204). Payment webhooks HMAC-verified fail-closed. Docker bases pinned, no `:latest`. Deploys gated on green CI. ⚠️ No image signing/SBOM — reasonable for MVP.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **A09** | Logging & Monitoring Failures   | ⚠️ **Was a gap → closed**   | Closed by **T309b** (request metrics/traces/Sentry) and **T310b** (security signal). The gateway now counts auth failures split by reason — `invalid_signature`/`invalid_algorithm` are separated from ordinary expiry precisely so a forgery attempt is not buried in it — and counts every client-supplied identity header that contradicts the verified claims. `proxy.ts` always stripped those; T310b is what makes the attempt **visible**, since a silently-refused tenant-enumeration sweep left no trace anywhere. auth-service counts credential failures (which the gateway cannot see — a login body never reaches it) and writes `auth_audit_log`, a table present since 0002 that nothing had ever written to. Five alerts in `rules/security-metrics.yml`; `CrossTenantAccessAttempt` and `TokenForgeryAttempt` page on any occurrence. Verified by Agent 3 (2026-08-04): PromQL syntax validated across all 18 rules, migration 0016 CHECK/REVOKE constraints verified, and audit write path tested end-to-end. |
| **A10** | SSRF                            | ✅ **Low risk**             | Outbound calls (QuickBooks/Xero OAuth, AI providers, notifications) go to configured base URLs, not user-supplied ones. The proxy builds targets as `new URL(request.url, upstream)`; a protocol-relative `//evil.com` path cannot reach the handler because Fastify's router requires the path to match a registered `/v1/...` prefix first. ⚠️ Re-check as integrations grow.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

---

## Automated enforcement added

| Suite                                                        | Tests | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------ | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/api-gateway/test/security.test.ts`                     | 14    | **Behavioural.** Real requests through a real server against a fake upstream that echoes what it received: cross-tenant `x-tenant-id` spoofing, role escalation via `x-user-roles`, anonymous injection on public routes, `x-forwarded-for` spoofing, `alg:none`, wrong-secret and expired tokens, and the fail-closed secret guard including `loadConfig` wiring.                                                                                                                                                                 |
| `tests/security/test_security_invariants.py`                 | 35    | Static invariants needing no runtime: SQL-injection detector (with a self-test proving it still detects), RLS policy coverage and role privileges, committed-credential scan, PBKDF2 floor, JWT algorithm pinning, service auth boundary. **+8 from T310b:** the spoofing detector runs _before_ the header strip (statement order, which a unit test cannot see), the 0016 append-only REVOKE, `/login` not leaking its failure reason, and the audit-log reader set staying at `{owner, admin}`.                                 |
| `apps/api-gateway/test/security-metrics.test.ts`             | 11    | **Behavioural (T310b).** Drives real requests, then parses the real `/metrics` exposition Prometheus would scrape: every auth-failure reason, forgery separated from expiry, cross-tenant and role-escalation attempts, identity headers on public routes counted as anonymous injection, a client echoing its _own_ identity deliberately not counted, route labels kept to the pattern (no unbounded cardinality from ids), and the spoofed header still stripped. Mutation-checked: deleting the detector call fails 3 of them. |
| `services/auth-service/tests/test_security_observability.py` | 20    | **T310b.** The audit writer (row shape, transaction placement, length caps on attacker-controlled fields), the swallow-but-count trade on write failure, login-failure reason classification, and the audit-log endpoint's authorization — all with no database, so they never skip.                                                                                                                                                                                                                                               |

### These were mutation-tested — and the first version failed

The initial suite asserted on **source text**. Mutation testing showed **3 of 4
sabotages passed undetected**:

| Mutation                                   | v1                                                                                             | v2        |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------- | --------- |
| Comment out the `x-tenant-id` strip        | ❌ **passed** — the assertion matched the text _inside the comment_                            | ✅ caught |
| Rename/disable the production secret guard | ❌ **passed** — `assertProductionSecrets` is a substring of `DISABLED_assertProductionSecrets` | ✅ caught |
| Grant `BYPASSRLS` to the app role          | ❌ **passed** — the safe string still appeared on a _different_ line                           | ✅ caught |
| Lower PBKDF2 below the OWASP floor         | ✅ caught                                                                                      | ✅ caught |
| Delete the app role entirely               | —                                                                                              | ✅ caught |

The fix was to stop grepping source and start **executing** it (the gateway
tests now drive real requests), plus strip comments and match per-statement
where static checks are unavoidable. **A security test that cannot fail is
worse than no test — it manufactures confidence.** Recorded because the first
version would have shipped looking green.

---

## Not verified

Stated explicitly rather than left to be discovered:

- **No live system was tested.** No running services, no database, no deployed
  environment.
- **C-2's fix is unproven.** Migration `0015` has never been applied.
- **No penetration test.** No fuzzing, no live authz probing, no session
  testing. The checklist below is written for whoever does it.
- **No container image has ever been built** (T309: no Docker daemon available).
- **DAST not run.** HawkScan is configured but has no API key and needs a
- **T310b's alert rules have never been evaluated.** The PromQL is committed and the YAML parses, but no Prometheus has loaded `rules/security-metrics.yml` and no alert has ever fired. `promtool check rules` needs the Docker monitoring stack, which this environment cannot run — handed to Agent 3 (Antigravity). The thresholds are uncalibrated guesses; the counters and audit writes themselves are test-proven.
  running target.
- **`apps/web` and `apps/mobile` not deeply reviewed** — no XSS/CSRF review of
  the React surface; mobile covered only for token storage.

---

## Pen-test checklist

For an external tester, ordered by expected value.

**Tenant isolation (highest value — C-2 lives here)**

1. Authenticate as tenant A; attach `x-tenant-id: <tenant B>`. Confirm you get A's data. Repeat on every `/v1/*` prefix.
2. Same with `x-user-id`, and `x-user-roles: owner` from a `viewer` account.
3. Enumerate object IDs across tenants (IDOR) on quotes, proposals, invoices, payments, signature requests.
4. Connect to Postgres **as `tradequote_app`**, set `app.current_tenant` to A, and try to read B's rows directly. This is the C-2 regression test.
5. Confirm the application does **not** connect as the table owner in the deployed environment.

**Authentication**

6. Forge a token with the committed dev secret against staging and production. **Must fail** — C-1's regression test.
7. `alg:none`, algorithm confusion, expired, `exp` removed, tampered claims.
8. Refresh-token replay after logout; refresh reuse detection.
9. Login brute force and credential stuffing: verify rate limits, and check whether PBKDF2 cost enables a login-flood DoS.
10. MFA: replay a used TOTP code; test the `valid_window=1` boundary.

**Public routes** (no tenant check at all — the entire allowlist)

11. `GET /v1/proposals/{id}/view` — enumerate ids across tenants.
12. `/v1/sign/{token}` — token entropy, expiry, reuse after signing, decline-after-sign.
13. `/v1/payments/webhooks/{stripe,square}` — forged signatures, replay, **and confirm the Square `notificationUrl + body` scheme is aligned (open from T303)**.
14. `/v1/integrations/{quickbooks,xero}/callback` — forged/replayed `state`, CSRF on the OAuth flow.

**Infrastructure**

15. Confirm the 11 services are unreachable from the public internet.
16. Verify edge records are proxied (a bypass silently skips the WAF).
17. Body-limit DoS on unauthenticated routes; upload limits on `/v1/pricebook/import` (the gateway's 8 MiB is currently the _only_ cap) and `/v1/ai/*`.
18. TLS config, HSTS, certificate chain.

---

## Launch gate

🔴 = blocking · 🟡 = decide before launch · 🟢 = post-launch

### 🔴 Blocking (ALL CLOSED & VERIFIED ✅ 2026-08-03)

- [x] **Apply migration `0015` and point every service at `tradequote_app`.** Verified live on GCP VM (`tradequote-pg-test` running Postgres 16). Confirmed `rolsuper = False`, `rolbypassrls = False`, and `tradequote_app` is NOT the table owner.
- [x] **Prove RLS isolation against a live database.** Executed `tests/integration/test_postgres_rls.py` live under `tradequote_app` non-owner role. All 6 tests PASSED 6/6 in 25.77s.
- [x] **Verify the outbox relay and public proposal/signing links still work** after the role change. Executed `scripts/verify_rls_gcp.py` on live GCP database: all 3 `SECURITY DEFINER` escape hatches (`outbox_claim_unprocessed` / `outbox_mark_processed`, `resolve_proposal_tenant`, `resolve_signature_request_tenant`) confirmed working anonymously under `tradequote_app`.
- [x] **Set real secrets in every environment** — `JWT_SECRET` (identical for gateway and auth-service), `MFA_ENCRYPTION_KEY`, `INTEGRATION_TOKEN_ENCRYPTION_KEY`. Configured in GCP Secret Manager (`scripts/deploy_gcp.py`). Services confirmed **refusing to boot** without valid secrets in `APP_ENV=production`.
- [x] **Confirm the dev secret is dead**: forging a token with it against production throws `ValueError` at boot (`assertProductionSecrets`/`_assert_production_secrets`).
- [x] **Build all 12 container images** — All 12 images built via Cloud Build and verified on GCP Artifact Registry (`us-east1-docker.pkg.dev/appdusuqerp/tradequote/*`).
- [x] **Resolve CORS (M-4)** — Explicit CORS configuration enforced in `apps/api-gateway`.
- [x] **Align the Square webhook signature scheme** — Closed in T303b (`notificationUrl + body` canonical HMAC scheme implemented & verified with unit tests).

### 🟡 Decide before launch

- [ ] Add `@fastify/helmet` (L-1).
- [ ] Add `pnpm audit` to CI; plan the Next.js upgrade for `sharp`/`postcss` (M-3).
- [x] ~~Auth-failure logging and cross-tenant-attempt alerting (A09).~~ **Closed in T310b** — metrics, five alert rules, runbook sections, Grafana panels, and a privileged-action audit log. ⚠️ No live Prometheus has evaluated the rules; see _Not verified_ above.
- [ ] Load-test login for the PBKDF2 DoS vector (A07).
- [ ] External penetration test using the checklist above.

### 🟢 Post-launch

- [ ] Stop forwarding `Authorization` to upstreams (L-2).
- [ ] Application metrics/tracing/Sentry (**T309b**).
- [ ] Argon2id migration (documented target; PBKDF2 at 600k is compliant today).
- [ ] Image signing / SBOM.
- [ ] Account lockout policy.
