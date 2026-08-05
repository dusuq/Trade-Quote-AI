# 🔀 Handoff — T309 + T310: build, verify and deploy on **GCP**

- **From:** Claude Code (Opus 5)
- **To:** **Agent 3 — Google Antigravity (Gemini)**
- **Assigned:** 2026-08-03
- **How to use this file:** paste this whole document as the first message into
  your next Google Antigravity session.

---

## Why you're getting this

Everything Docker-, deploy-, and live-verification-shaped is now yours, because
none of it can be done in the authoring environment:

- **No Docker daemon.** `docker ps` fails to connect; Docker Desktop was
  launched and polled for ~4 minutes without the daemon coming up. So **not one
  of the 12 container images has ever been built.**
- **No Android emulator** (`flutter emulators` finds none).
- **No live Postgres**, so the RLS suite `skipif`s itself — which is exactly how
  the T310 critical finding stayed hidden.

You have GCP, and you have already done this shape of work: **T002b** (dev-stack
smoke test on GCP) and **T311** (live-Postgres RLS pass on
`tradequote-pg-test`, `us-east1-b`, as role `tradequote_app`).

### ⚠️ Read this first: T309 targets Fly.io, you're deploying to GCP

T309 was authored against **Fly.io** (per `docs/05-TECH-STACK.md`, which lists
Railway/Fly.io for MVP). The instruction now is **GCP**. That is a real gap, not
a detail — see [Retargeting to GCP](#retargeting-to-gcp) for exactly what
carries over and what does not. **The Dockerfiles are portable and are the bulk
of the value; the `fly.toml` files are not.**

---

## Three things are being handed over

| #   | What                                                     | State                                                                   |
| --- | -------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1   | **T309** — containers, deploy pipeline, monitoring, edge | Built, `IN_REVIEW`, **never built or deployed**                         |
| 2   | **T310** — security review + OWASP + launch gate         | Findings fixed in code; **one critical fix unverified**                 |
| 3   | **T301b/T302** — mobile offline→online sync cycle        | Was handed to you separately; folded in here since it also needs Docker |

---

## 1. T309 — build the images (highest value, do this first)

The single most valuable thing you can do. 12 Dockerfiles, zero build attempts.

```bash
# Python services (build context = the service dir)
for d in services/*/; do
  n=$(basename "$d")
  echo "=== $n ==="
  docker build -t "tradequote-$n:test" "$d" || echo "FAILED: $n"
done

# Gateway — build context is the REPO ROOT (pnpm workspace: it needs the
# lockfile and packages/* that live above apps/api-gateway).
docker build -f apps/api-gateway/Dockerfile -t tradequote-api-gateway:test .
```

**What I expect might break**, so you know where to look:

- `proposal-service` — `reportlab` + `qrcode[pil]` pull in Pillow. manylinux
  wheels usually bundle their native deps, but this is the most likely image to
  need extra system libraries.
- `analytics-service` — the only service using `psycopg2-binary` rather than
  `psycopg[binary]`.
- **5 services have no `uv.lock`** (`analytics`, `auth`, `customer`, `esign`,
  `pricebook`), so their builds resolve dependencies at build time and are not
  byte-reproducible. If you have to touch them anyway, committing a lock is a
  cheap win.
- The gateway does `pnpm --filter @tradequote/api-gateway --prod deploy /out`.
  Confirm `/out` contains `dist/`, `node_modules/`, and `package.json`.

Then check the hardening actually holds in a running container:

```bash
docker run --rm tradequote-auth-service:test id          # expect uid=10001, NOT root
docker run --rm -e PORT=9999 -p 9999:9999 tradequote-auth-service:test &
curl -fsS http://127.0.0.1:9999/health                    # $PORT must be honoured
```

That `$PORT` check matters: I changed the CMD to
`sh -c "exec uvicorn ... --port ${PORT:-<registry port>}"` **specifically so
these images work on Cloud Run**, which injects `$PORT` and ignores `EXPOSE`.
The `exec` is load-bearing — without it the shell stays PID 1, swallows
SIGTERM, and every deploy waits out the full termination grace period instead
of draining. Please verify a `docker stop` exits promptly.

---

## 2. T310 — the security work you must verify

Full detail: [docs/13-SECURITY-REVIEW-OWASP.md](../13-SECURITY-REVIEW-OWASP.md).
Two critical findings, both fixed in code. **One of them you are the only person
who can confirm.**

### 🔴 C-2 — RLS was silently bypassed. Your T311 environment is why it looked fine.

Every tenant table has `ENABLE ROW LEVEL SECURITY`, but **`ENABLE` does not
apply to the table owner — only `FORCE` does.** Migrations run as
`DATABASE_URL`, so that role owns every table, and the services' default
`DATABASE_URL` is _the same role_.

Your T311 run proved the policies genuinely work — but it connected as
`tradequote_app`, **a role you created by hand that exists in no migration**.
The only trace of it in the repo is the hardcoded default URL in
`tests/integration/test_postgres_rls.py`. So the control works exactly where
someone remembered to build it, and silently vanishes everywhere else.

**`infra/db/migrations/0015_rls_app_role.sql` codifies that role** —
deliberately the same name, so your existing environment keeps working.

**I did NOT add `FORCE ROW LEVEL SECURITY`, on purpose.** Three
`SECURITY DEFINER` functions rely on the owner exemption as their intended
escape hatch, and `FORCE` would silently break all three:

| Function                                                    | Breaks                                                                                                                             |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `outbox_claim_unprocessed` / `outbox_mark_processed` (0012) | The relay is cross-tenant with no tenant context → matches zero rows → publishes nothing. **This is the T205c bug, reintroduced.** |
| `resolve_proposal_tenant` (0006)                            | Public proposal `/view` links                                                                                                      |
| `resolve_signature_request_tenant` (0008)                   | Public e-signature signing links                                                                                                   |

**What I need from you:**

```bash
# 1. Apply the new migration
DATABASE_URL="postgresql://<owner>@<host>:5432/tradequote" bash infra/db/run-migrations.sh

# 2. Confirm the role is genuinely non-privileged
psql "$DATABASE_URL" -c "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname='tradequote_app';"
#    expect: rolsuper = f, rolbypassrls = f

# 3. Confirm the app role does NOT own the tables (this is the whole finding)
psql "$DATABASE_URL" -c "SELECT tablename, tableowner FROM pg_tables WHERE schemaname='public' LIMIT 10;"
#    tableowner must NOT be tradequote_app

# 4. Give it a login credential (never commit it; Secret Manager or IAM auth)
psql "$DATABASE_URL" -c "ALTER ROLE tradequote_app WITH LOGIN PASSWORD '<from Secret Manager>';"

# 5. Re-run the RLS suite AS that role
TEST_DATABASE_URL="postgresql+psycopg://tradequote_app:<pw>@<host>:5432/tradequote" \
  python -m pytest tests/integration/test_postgres_rls.py -v
```

🔴 **Then the part that actually worries me** — confirm the role change did not
break the owner-exemption escape hatches:

- The **notification outbox relay** still claims and publishes events (T205c
  regression).
- A **public proposal `/view`** link still resolves with no tenant context.
- A **public `/v1/sign/{token}`** link still loads and can be signed.

If any of those break, that is the side effect I flagged, and it needs fixing
before launch — not working around by granting the role more privilege.

### C-1 — publicly known JWT secret (fixed; please confirm it's dead)

The gateway and auth-service both defaulted `JWT_SECRET` to the same literal
committed in this public repo, with **no production guard anywhere**. Anyone
could forge a token with any `tid` and `roles`; the gateway would verify it and
inject the forged tenant downstream as trusted.

Services now **refuse to boot** in `production`/`staging` on dev defaults.
That is the intended behaviour — a service failing to start with a clear
message means the guard is working, not that the deploy is broken.

Please confirm on GCP:

1. Deploy **without** `JWT_SECRET` → the container must fail to start with
   `Refusing to start ... insecure configuration`.
2. Deploy **with** real secrets → boots normally.
3. Forge a token with `local-dev-only-change-me-32byte-minimum-secret` against
   the deployed gateway → **must 401**.

Secrets required per environment (see the launch gate for the full list):
`JWT_SECRET` (identical for gateway **and** auth-service),
`MFA_ENCRYPTION_KEY`, `INTEGRATION_TOKEN_ENCRYPTION_KEY`.

---

## Retargeting to GCP

What carries over from T309, and what you'll need to build.

| T309 (Fly.io)                                    | GCP equivalent                                          | Carries over?                                           |
| ------------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------------- |
| `Dockerfile` × 12                                | Same images                                             | ✅ **Yes, unchanged** — now `$PORT`-aware for Cloud Run |
| `.dockerignore` × 12                             | Same                                                    | ✅ Yes                                                  |
| `infra/services.yml` registry                    | Same source of truth                                    | ✅ Yes — ports, memory, criticality all still apply     |
| `fly.toml` × 12                                  | Cloud Run service YAML / `gcloud run deploy` flags      | ❌ **No** — rewrite needed                              |
| Fly private `.internal` network                  | Cloud Run **internal ingress** + service-to-service IAM | ❌ Rewrite                                              |
| Fly Postgres                                     | **Cloud SQL** (you already have `tradequote-pg-test`)   | ❌ Rewrite                                              |
| Fly secrets                                      | **Secret Manager**                                      | ❌ Rewrite                                              |
| Cloudflare WAF/rate limits (`infra/cloudflare/`) | **Cloud Armor**, or keep Cloudflare in front of the LB  | 🟡 Either                                               |
| `deploy.yml` (flyctl)                            | `gcloud run deploy` / Cloud Build                       | 🟡 Structure reusable, commands not                     |
| Prometheus/Grafana/Loki stack                    | **Cloud Monitoring/Logging**, or run the stack as-is    | 🟡 Your call                                            |

**Cloud Run is the natural target** — these are stateless HTTP containers with
`/health` endpoints, which is exactly its shape. GKE would work but is far more
operational overhead than this workload justifies at MVP.

Mapping the registry onto Cloud Run:

```bash
# infra/services.yml drives all of this — read it, don't hardcode.
gcloud artifacts repositories create tradequote --repository-format=docker --location=us-east1

gcloud run deploy tradequote-auth-service \
  --image us-east1-docker.pkg.dev/$PROJECT/tradequote/auth-service:$TAG \
  --region us-east1 \
  --port 8001 \
  --ingress internal \                        # private: only the gateway may call it
  --no-allow-unauthenticated \
  --min-instances 1 \
  --memory 512Mi \
  --set-secrets "JWT_SECRET=tq-jwt-secret:latest,DATABASE_URL=tq-db-url:latest"

# The gateway is the ONLY public unit.
gcloud run deploy tradequote-api-gateway \
  --image us-east1-docker.pkg.dev/$PROJECT/tradequote/api-gateway:$TAG \
  --region us-east1 --port 8000 \
  --ingress all --allow-unauthenticated \
  --min-instances 2
```

Two things to get right, because they're where the security model lives:

1. **Only `api-gateway` may be public.** All 11 services must be
   `--ingress internal` + `--no-allow-unauthenticated`. `infra/services.yml`'s
   `public: true` flag marks the single exception, and `tests/infra` asserts
   there is exactly one. If a service ends up publicly reachable, every
   authorization guarantee in the system is void — downstream services trust
   `x-tenant-id` blindly by design.
2. **`min-instances ≥ 2` for the gateway and payment-service.** A cold-starting
   payment webhook handler drops provider callbacks that aren't reliably
   retried. This is encoded as `min_machines` / `critical: true` in the registry.

---

## 3. T301b/T302 — mobile sync cycle (folded in)

Detail in
[T301b-T302-mobile-live-verification-antigravity-handoff.md](T301b-T302-mobile-live-verification-antigravity-handoff.md).
Short version: `flutter analyze` clean, `flutter test` 40/40, secure token
persistence implemented and unit-tested. What's left needs an emulator + a
running gateway: login → offline edits → reconnect → confirm the sync queue
replays and last-write-wins holds while server-authoritative money fields stay
server-side.

If you're standing up a GCP gateway anyway, point the emulator at it (the app
defaults to `http://10.0.2.2:8000`, the Android-emulator host alias — you'll
need to override that for a remote host; it's a hardcoded constant in
`api_client.dart`, `auth_state.dart`, and `sync_bootstrap.dart`).

---

## Current gate status (all green in the authoring environment)

| Gate                                               | Result                               |
| -------------------------------------------------- | ------------------------------------ |
| `python -m pytest tests/infra -q`                  | **51 passed**                        |
| `python -m pytest tests/security -q`               | **27 passed**                        |
| `apps/api-gateway` · `pnpm vitest run`             | **53 passed** (14 new security)      |
| `apps/mobile` · `flutter analyze` / `flutter test` | clean / **40 passed**                |
| `python scripts/gen_infra.py --check`              | OK — 38 artifacts match the registry |
| `python scripts/check_conventions.py`              | OK                                   |

Both new suites were **mutation-tested**. Worth knowing: the security suite's
first version was checking source _text_, and **3 of 4 sabotages passed
undetected** (an assertion matched the protection inside its own comment). It
was rewritten to execute real requests. If you extend it, apply the same test:
break the thing on purpose and confirm the test fails.

**Please re-run all of these after any change you make**, plus
`python scripts/gen_infra.py --check` if you touch a Dockerfile — generated
artifacts must stay in sync with `infra/services.yml` or CI rejects the deploy.

---

## What to report back

1. **Build results for all 12 images** — pass/fail per image, plus the fix for
   any that failed.
2. **The C-2 verification** — the four `psql` checks above, the RLS suite run as
   `tradequote_app`, and explicitly whether the outbox relay + public
   proposal/signing links still work.
3. **The C-1 verification** — that the boot guard fires, and that a token forged
   with the dev secret is rejected.
4. **Whatever you deployed** — service URLs, and confirmation that the 11
   services are not publicly reachable.
5. Update `TASKS.md` + `tracking/PROGRESS-TRACKER.csv` for T309 (currently
   `IN_REVIEW`) and T310, and tick the 🔴 items in
   [the launch gate](../13-SECURITY-REVIEW-OWASP.md#launch-gate) that you close.

## Standing rules

- If you find a bug, prefer reporting it precisely (file, line, repro) over
  silently patching around it; if it's a one-liner, say clearly in the commit
  message what you touched and why.
- **Never commit a real secret.** Secret Manager or IAM auth only. The dev
  defaults in config files are deliberate and guarded — leave them.
- Don't "fix" a service that refuses to boot on dev secrets by weakening the
  guard. That refusal is the feature.
