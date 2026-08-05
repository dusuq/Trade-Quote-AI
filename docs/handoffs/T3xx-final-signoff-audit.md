# CTO Audit — Final sign-off of the developed backlog (T303b · T308b · T309 · T309b · T310 · T310b · T311 · T311b · T313 · T313b · T313c)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-08-04
- **Baseline:** full sweep **11 services green** (`ruff check .` / `mypy .` / pytest — now byte-identical to CI), gateway **69**, web **149**, mobile **40**. Working tree clean, synced with origin.

Two categories: **independently verified here**, and **code-verified + resting on the fleet's recorded live-GCP evidence** (the GCP VM/registry cannot be reproduced from this machine — the same standard applied to T002b since the start).

---

## ✅ Independently verified here

### T303b — payment webhooks: canonical Square HMAC + idempotent capture
- **payment-service 23/23** (was 12). Square now HMACs the **canonical `notificationUrl + rawBody`** with the URL taken from config, never a header — a forger can't supply the string their own signature was computed against. Tests pin it: `rejects_the_old_body_only_scheme` (proves the canonical scheme is *enforced*, not just documented) and `accepts_a_correctly_signed_body` as a positive control.
- Idempotency: `payment_webhook_event` (unique `provider, event_id`) + `record_webhook_event()` / `DuplicateWebhookEventError`; a replayed event skips the mutation and still 200s.
- The whole webhook-security surface remains mutation-tested (reverting to the pre-fix handlers fails the rejection tests). **Signed off.**

### T308b — integrations: real OAuth + token encryption
- **integration-service 53/53** (was 10). Real OAuth2 authorization-code + refresh-rotation for QuickBooks and Xero via `OAuthProvider`/`InvoiceSyncClient` ports; outbound HTTP through `ProviderHttpClient` (the ADR-0003 pattern — explicit timeout, POST never replayed after timeout, failures mapped).
- **The T308 open question is answered:** `FernetTokenCipher` (`cryptography.fernet`, AES-128-CBC + HMAC-SHA256, authenticated) keyed from `INTEGRATION_TOKEN_ENCRYPTION_KEY` — tokens are **genuinely encrypted at rest**, not a column named `_encrypted`. Zapier stays API-key/webhook per brief. **Signed off.**

### T309b — observability wiring
- `/metrics` always mounted (Instrumentator), OTel tracing opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT` incl. gateway→service `traceparent` propagation, Sentry opt-in via `SENTRY_DSN`. Per-service `test_observability` green in the sweep. The report is honest that live Sentry/OTel/Prometheus *delivery* isn't verified here — the **wiring** is. **Signed off** on that scope.

### T310b — OWASP A09 security observability
- Gateway `auth_failures_total{reason,route}` + `cross_tenant_attempts_total`; auth-service login attempt/failure counters — covered by the gateway's 69 tests and auth `test_security_observability`.
- **Migration 0016** REVOKEs `UPDATE, DELETE, TRUNCATE` on `auth_audit_log` from `tradequote_app` (TRUNCATE explicitly, since it bypasses row DELETE policies) — the audit log is append-only to the app role. Correct. **Signed off.**

### T313 / T313b / T313c — tooling & the gate divergence
- **T313:** the real finding was that the sweep ran `ruff check app` while CI ran `ruff check .`, so **CI was already red on analytics-service while the sweep printed green**. Fixed by making the sweep byte-identical to CI (`ruff check .`, `mypy .`) — verified in `run_all_tests.py`. Root `tests/`/`scripts/` now governed by a `ruff.toml`. **Signed off.**
- **T313b:** `prettier --check` → *"All matched files use Prettier code style!"*; flat ESLint 9 configs added for web/gateway/types/config. **Signed off.**
- **T313c:** `scripts/verify_rls_gcp.py` reads `APP_PASS = os.getenv("APP_PASS", "")` — **no hardcoded credential**; `deploy_gcp.py` uses GCP Secret Manager *references* (`tq-db-url:latest`), not values. **Signed off.** (This is the follow-through on the earlier committed-credential incident: scripts are now clean.)

---

## ✅ Code-verified; live-GCP claims rest on the fleet's recorded evidence

These make claims about a running GCP Postgres VM and Artifact Registry that cannot be reproduced from this machine. I verified the **code/migrations/tests** are correct and that the suites **skip gracefully** without live infra; the live results are accepted on the recorded evidence, exactly as T002b was.

### T309 — GCP Cloud Run deployment
- `tests/infra` **63 passed** (Dockerfile/registry/deploy scaffolding). `deploy_gcp.py` maps services onto Cloud Run + Secret Manager + IAM, internal ingress for the 11 services and public only for the gateway — correct topology. The "12 images on `us-east1-docker.pkg.dev/...`" claim rests on the fleet's evidence. **Signed off** (code + topology verified; live push on evidence).

### T310 — launch-gate closure
- **Migration 0015** creates `tradequote_app NOLOGIN NOSUPERUSER NOBYPASSRLS` with the password deliberately *not* committed (granted per-environment from Secret Manager) — the correct RLS posture, and the linchpin of the whole tenant-isolation model. Live apply to the GCP VM + 6/6 live RLS pass rest on evidence. **Signed off** (migration verified; live apply on evidence).

### T311 / T311b — live-Postgres RLS verification
- `tests/integration/test_postgres_rls.py` **skips gracefully (8 skipped)** with no live DB and, since the credential incident, **no hardcoded secrets** (localhost default, real DSN via `TEST_DATABASE_URL`). The suite structure is correct — RLS isolation, `WITH CHECK` write-blocking, the SECURITY DEFINER resolvers, T206b enum round-trip, T201 `ai_usage_log`, T307b analytics. The live pass on GCP Postgres 16 rests on the fleet's recorded evidence. **Signed off** (suite verified; live run on evidence).

---

## Standing items (not blockers to these sign-offs)
- **The earlier committed DB credential** (commit `3b0eb8d`) is out of HEAD but remains in **pushed history** — rotate `tradequote_app` / review `34.24.115.216`; history rewrite is a separate authorized op. T313c confirms *scripts* are now credential-free.
- Live delivery of metrics/traces to a real Prometheus/OTel/Sentry backend, and an on-device mobile offline→online sync cycle, remain the honest "not reproducible here" gaps their own reports already name.
