# T313 — Tooling / lint sweep: completion notes + Antigravity handoff

**Date:** 2026-08-03
**Task:** T313 — lint test code in the sweep
**Status:** T313 itself is **complete and verified on this machine.** This document
records (a) what was done, (b) what physically cannot be verified here and is
handed to Google Antigravity, and (c) adjacent gate failures found while doing
it that are _not_ handoff items — they are fixable anywhere and are filed as
follow-ups rather than silently absorbed into this task.

---

## 1. What T313 changed (verified here)

The original finding: `scripts/run_all_tests.py` ran `ruff check app`, so **no
service's `tests/` directory had ever been linted**, while the sweep printed
"all services passed".

Worse than recorded: **CI already ran `ruff check .`** (`.github/workflows/ci.yml`,
Python lane), which _does_ cover tests. So the two gates disagreed, and CI was
already red on `analytics-service` while the local sweep reported success. A
local gate weaker than the remote one is worse than no local gate — it
manufactures confidence rather than merely failing to provide it.

| Change                                                                    | File                                                   |
| ------------------------------------------------------------------------- | ------------------------------------------------------ |
| Sweep lints whole service dir (`ruff check .`), matching CI byte-for-byte | `scripts/run_all_tests.py`                             |
| Sweep typechecks `mypy .`, matching CI                                    | `scripts/run_all_tests.py`                             |
| New repo-root lint lane for `tests/` + `scripts/`                         | `scripts/run_all_tests.py`, `.github/workflows/ci.yml` |
| Explicit repo-root ruff config (rules named, not inherited)               | `ruff.toml` (new)                                      |
| Regression guard, mutation-tested                                         | `tests/infra/test_sweep_coverage.py` (new)             |
| analytics-service test lint fallout cleared                               | `services/analytics-service/tests/*`                   |
| `F841` in the RLS verifier                                                | `scripts/verify_rls_gcp.py`                            |

**Two coverage holes closed, not one.** Beyond service `tests/`, the repo-root
`tests/` and `scripts/` trees had **no ancestor ruff config at all** — including
`tests/infra` and `tests/security`, which CI _executes_ on every push. They were
linted by nothing. `ruff.toml` now governs them, and names its rules explicitly
because ruff's defaults shift between releases (see §3.3).

### Verification run here

- `python scripts/run_all_tests.py` → **11/11 services green** (pytest + ruff + mypy) **+ repo-root lint green**
- `python -m pytest tests/infra -q` → **63 passed** (54 prior + 9 new guard tests)
- `python scripts/check_conventions.py` → OK
- `python scripts/gen_infra.py --check` → OK (40 artifacts)
- `pnpm --filter @tradequote/api-gateway test` → **58/58**
- `pnpm typecheck` → 3/3 packages clean

**The guard is mutation-tested.** Reverting the sweep to `ruff check app` fails
**3 independent tests** in `tests/infra/test_sweep_coverage.py`; restoring it
turns them green again. It is not a test that merely re-states the source.

---

## 2. HANDOFF TO ANTIGRAVITY — cannot be verified on this machine

These are blocked by the environment, not by missing work. Each lists the exact
blocker so nobody re-litigates whether it was skipped out of laziness.

### 2.1 Docker image builds (12 units) — **BLOCKED: daemon unreachable**

```
docker --version   ->  Docker version 29.5.2, build 79eb04c   (CLI present)
docker info        ->  daemon: UNREACHABLE
```

The CLI is installed but no daemon is running, so **no image in this repo has
ever been built** — still true from T309. `tests/infra` validates the
Dockerfiles _structurally_ (non-root `USER app`, pinned bases, `EXPOSE` matches
the registry port, `HEALTHCHECK` present, `exec uvicorn` for signal handling)
but structure is not a build.

**Asked of Antigravity:**

1. `docker build` all 12 units (11 Python + the gateway, which builds from the **repo root** — it is a pnpm workspace package).
2. Report any missing system libraries — `proposal-service` (reportlab/Pillow) and `ai-service` (model SDKs) are the likely first failures.
3. Confirm each container starts and answers `/health`, and that the new **`/metrics`** endpoint (T309b) responds inside the container.
4. Confirm the image drops privileges (`whoami` → `app`, uid 10001).

### 2.2 Live-Postgres suites — **BLOCKED: no database, and they skip silently**

`TEST_DATABASE_URL` is unset. `tests/integration/test_postgres_rls.py` **skips
silently** when there is no DB — CI's own comment calls this out as "exactly how
the RLS finding hid". A silent skip inside a gate is the same bug class T313
just fixed, so treat a green run with no DB as _no evidence at all_.

**Asked of Antigravity** (this is **T311b**'s substance; listing it here so the
Docker session can knock it out while a database is already up):

1. Stand up Postgres 16, apply migrations `0001`–`0015` (note **`0015_rls_app_role.sql`** from T310 has _never_ been applied anywhere).
2. Connect as the non-owner `tradequote_app` role and re-run the RLS suite.
3. Verify the T206b enum round-trip **through SQLAlchemy** (write a `QuoteStatus` via the ORM, read it back, assert the stored label is lower-case) — the current test inserts the literal string via raw SQL and passes with or without the fix.
4. Exercise `summarize_quotes()` / `resolve_range()` including a timezone-boundary case.
5. Add `ai_usage_log` RLS coverage.

### 2.3 GCP Cloud Run deploy — **BLOCKED: outward-facing, needs project credentials**

`gcloud` 572.0.0 is installed, but deploying is an outward-facing action against
real infrastructure and is deliberately **not** something I will trigger.
`scripts/deploy_gcp.py` and `scripts/build_all_gcp.py` are ready.

**Asked of Antigravity:** deploy, then confirm the post-deploy `/health` smoke
test and that the gateway reaches each service on its registry port.

### 2.4 Live observability backends (T309b's open item) — **BLOCKED: no collector/project**

T309b wired OTel + `/metrics` + Sentry across all 12 units and the wiring is
unit-tested (init paths, a real W3C `traceparent` on the wire between gateway
and service), but **nothing has ever been delivered to a real backend.**

**Asked of Antigravity:**

1. Run the monitoring stack (`pnpm monitor:up`) and confirm Prometheus actually scrapes the new **`app-metrics`** job (targets in `infra/monitoring/prometheus/targets/app-metrics-*.json`).
2. Confirm the 3 new Grafana panels render (request rate / 5xx rate / p99 latency).
3. Point `OTEL_EXPORTER_OTLP_ENDPOINT` at a collector and confirm a gateway→service trace arrives as **one** trace, not two disconnected ones.
4. Set a real `SENTRY_DSN` and confirm an exception lands.

---

## 3. Tooling Follow-ups (`T313b`, `T313c`) — **COMPLETED by Agent 3 (2026-08-04)**

All local follow-up tooling tasks filed during the T313 audit have been resolved and verified:

### 3.1 `pnpm lint` — **RESOLVED (`T313b.1`)**

Wired flat ESLint 9 configuration files (`eslint.config.mjs`) across `@tradequote/web`, `@tradequote/api-gateway`, `@tradequote/types`, and `@tradequote/config`, and added `"lint": "eslint ."` to each package's `package.json`.

- `pnpm lint` (`turbo run lint`) now runs linting across all 4 workspace packages (4/4 green).
- Cleared 4 `apps/web` lint issues: ignored `next-env.d.ts`, removed inline `import()` type annotation in `copilot-panel.test.tsx`, cleaned unneeded `react-hooks` comment in `integrations-manager.tsx`, and converted `require()` to ES import in `tailwind.config.ts`.

### 3.2 `pnpm format:check` — **RESOLVED (`T313b.2`)**

Ran Prettier across the entire codebase (`pnpm format`). `pnpm format:check` is now **100% GREEN** across all 76 previously non-compliant files in `docs/`, `services/`, `apps/`, and `packages/`.

### 3.3 Ruff Version & Rule Selection — **RESOLVED (`T313c.1`)**

Repo-root `ruff.toml` explicitly names rules (`E4`, `E7`, `E9`, `F`, `I`, `UP`, `B`) and excludes build/virtualenv outputs across `tests/` and `scripts/`.

### 3.4 Hardcoded Credential in GCP Verifier — **RESOLVED (`T313c.2`)**

Updated `scripts/verify_rls_gcp.py` to read `APP_PASS`, `OWNER_PASS`, `DB_HOST`, and `TEST_DATABASE_URL` via `os.getenv`, removing hardcoded fallback secrets from source control. Passes `ruff check scripts/verify_rls_gcp.py`.

---

## 4. Note for whoever picks this up: the working tree is being edited concurrently

While verifying, `services/analytics-service/app/infrastructure/repositories.py`
**changed underneath me** between two reads — long inline tuples were refactored
into named variables, which I did not do. That is uncommitted **T307b** rework
(TASKS.md marks T307b `[~]`, code deliberately left uncommitted in the tree).

Consequences, stated plainly:

- I stayed out of `services/analytics-service/app/` entirely. My analytics changes are confined to `tests/` (import ordering).
- Any "green" result in this document is a **snapshot**, not a guarantee, for as long as another agent is mutating the same tree.
- Re-run `python scripts/run_all_tests.py` before trusting it.
