# ✅ TASKS.md — TradeQuote AI Master Task Board

**How to use this board**

1. Find the first unchecked task **in your agent lane** whose dependencies are all `[x]`.
2. Set its status to `IN_PROGRESS` here and in `tracking/PROGRESS-TRACKER.csv` (add start date).
3. Build to spec → pass Quality Gates → check the box `[x]`, set CSV row `DONE`, fill end date.
4. Then run **"Check for next task"** (bottom of file) to see what unblocked.

**Status legend:** `[ ]` TODO · `[~]` IN_PROGRESS · `[b]` BLOCKED · `[x]` DONE
**Agents:** A1=Opus 4.8 (CTO) · A2=Sonnet 5 · A3=Gemini (Antigravity) · A4=Opus+Sonnet 4.6

---

## 🧱 PHASE 0 — Foundation (Week 0)

- [x] `T000` **[A1]** Project scaffold + monorepo structure + AGENTS/CTO docs — _deps: none_ ✅ done at init
- [x] `T001` **[A1]** Monorepo tooling: pnpm workspaces + Turborepo + base tsconfig/eslint/prettier → ADR-0001 — _deps: T000_ ✅ verified (`pnpm install` + `turbo --dry` graph builds)
- [x] `T002` **[A4]** Local dev stack authoring (postgres+pgvector, redis, minio+bucket, opensearch, qdrant) — _deps: T000_ ✅ files complete + `docker compose config` valid
- [x] `T002b` **[A3 · Antigravity]** **Live smoke test of the dev stack on GCP** (local Docker Desktop unavailable) — _deps: T002_ ✅ **CTO-audited PASS** — 6/6 containers healthy + 5 DB extensions + MinIO bucket + 5 migrations verified live on GCP Compute Engine (VM properly torn down after)
- [x] `T003` **[A1]** Global domain-event schema + naming conventions → `packages/types` + `docs/03-DOMAIN-EVENTS.md` — _deps: T000_ ✅ verified (typechecks + builds)
- [x] `T004` **[A4]** GitHub Actions CI skeleton (JS/TS + Python + Flutter lanes) — _deps: T001_ ✅ verified (all 5 stages green locally)

## 🔐 PHASE 1 — MVP Core (Weeks 1–4)

- [x] `T101` **[A1]** M1 Auth-service: tenants, users, RBAC, JWT, MFA (FastAPI, Clean Arch) — _deps: T002_ ✅ security core 9/9 tests + ruff clean; ⏳ live app-to-DB run still pending (T002b proved migrations/infra, not per-service runtime)
- [x] `T102` **[A1]** M3 DB schema v1 (tenant/user/customer/property/pricebook/quote) + RLS migrations — _deps: T002_ ✅ 5 ordered migrations — **live-applied & confirmed on GCP under T002b** (schema_migrations: 5 rows)
- [x] `T103` **[A1]** M2 API Gateway routing + auth middleware + rate limiting (Fastify) — _deps: T101_ ✅ 14/14 tests + typecheck/build clean; live integration still pending a persistent dev DB
- [x] `T104` **[A2]** M4 Customer CRM service: CRUD, properties, contacts, notes, tags, timeline (FastAPI + Repository Pattern) — _deps: T102, T103_ ✅ 21/21 tests + ruff/mypy clean; gateway route wired; ⏳ live app-to-DB run still pending
- [x] `T105` **[A3]** M6 Pricebook service: materials/labor/equipment, regional pricing, import — _deps: T102, T103_ ✅ 5/5 tests + Clean Arch + regional pricing + CSV import — **fully signed off (T105b+T105c complete)**
- [x] `T105b` **[A3 · Antigravity]** Reconcile pricebook to gateway auth pattern (remove JWT decode → trust `x-tenant-id`) — _deps: T105_ ✅ done by Agent 3; guard clean, no `jwt` anywhere
- [x] `T105c` **[A1]** CTO audit of T105b — _deps: T105b_ ✅ verified: 0 jwt refs, dead config removed, gateway wired, `check_conventions.py` green → **T105 signed off**
- [x] `T106` **[A3]** M7 Quote engine: line items, tax, margin/markup, totals, versioning — _deps: T105_ ✅ 5/5 tests + calc engine + versioning + domain events — **CTO-audited** ([report](docs/handoffs/T106-quote-service-audit.md)): conventions-clean; 3 non-blocking follow-ups (R1–R3)
- [x] `T107` **[A1]** M9 PDF engine (reportlab + qrcode): branded PDF cover/scope/line-items/totals/warranty/terms/signature page — _deps: T106_ ✅ 14/14 tests (real PDF text-extraction via pypdf) + ruff/mypy clean; wired into gateway `/v1/proposals`; storage behind a Protocol (local disk now, S3-ready)
- [x] `T108` **[A1]** M12 Web app shell + design system (Next.js 15 + Tailwind + shadcn-style) + auth flows — _deps: T103_ ✅ 19/19 tests + typecheck clean; `next build` produces all 10 routes prerendered with zero errors; login/register wired to auth-service via gateway
- [x] `T109` **[A1]** M12 Quote builder UI (web): customer picker, dynamic line items, live subtotal, create/list/detail/send/accept/reject — _deps: T106, T108_ ✅ 45/45 tests + typecheck clean; `next build` 11 routes zero errors; **live-verified in-browser** (form interactivity + mocked-API rendering); ⚠️ one known gap — see [apps/web/README.md](apps/web/README.md#definition-of-done)
- [x] `T110` **[A3-Low]** M26 Seed data + fixture generator (sample pricebooks per trade) — _deps: T105_ ✅ **CTO-audited PASS** — Electrical/Plumbing/HVAC catalogs verified via real pricebook import (3/3); full suite 8/8 green

## 🤖 PHASE 2 — AI + Delivery (Weeks 5–8)

- [ ] `T201` **[A1]** M15 AI Quote Assistant: voice→text→structured scope→line items — _deps: T106_
- [ ] `T202` **[A1]** M16 AI Copilot: pricing/margin/missing-items/rewrite endpoints — _deps: T106, T201_
- [x] `T203` **[A2]** M8 Proposal Builder: templates, cover page, branding, terms, warranty — _deps: T107_ ✅ `proposal_template`/`proposal`/`proposal_version` persistence on top of T107's PDF engine — template CRUD, create/send/view lifecycle, and the public unauthenticated `GET /v1/proposals/{id}/view` link. 30/30 proposal-service tests + ruff/mypy clean; 71/71 web tests + typecheck clean + `next build` 14/14 routes zero errors; 19/19 gateway tests + typecheck clean; `packages/types` typecheck/build clean; `check_conventions.py` OK. **Separately from this task's own scope, found and fixed an app-wide bug in `apps/api-gateway`'s `registerServiceProxy`: its `${prefix}/*` wildcard mount never matched the bare prefix with no trailing segment, so every bare `GET`/`POST` to a collection endpoint (`GET /v1/quotes`, `POST /v1/customers`, etc. — not just the new proposal routes) 404'd through the real gateway, invisible until now because no prior task ran the full stack live and no gateway test exercised a bare-prefix request.** Fixed by registering the handler at both the bare prefix and the wildcard, with regression tests (`test/server.test.ts`). Spec: [docs/modules/M8-proposal-builder.md](docs/modules/M8-proposal-builder.md); plan: [docs/modules/M8-proposal-builder-plan.md](docs/modules/M8-proposal-builder-plan.md).
- [ ] `T204` **[A4]** M10 E-Signature + audit trail (IP, timestamp, hash chain) — _deps: T203_
- [ ] `T205` **[A4]** M22 Notifications: email + SMS delivery of quotes/proposals — _deps: T203_
- [x] `T206` **[A2]** M20 Dashboard: quotes today/pending/accepted/revenue/conversion — _deps: T106_ ✅ **CTO-audited & SIGNED OFF (2026-07-25)** — `GET /v1/quotes/summary` read model (tz-aware boundary math via client-supplied IANA zone) + live `/dashboard` page. Audit re-ran green: **29/29 quote-service + 61/61 web tests**, ruff/mypy/typecheck/`next build` clean, `check_conventions.py` OK. Route-ordering trap (`/summary` before `/{quote_id}`) handled **with a regression test**; full 200 body pinned by `test_summary_endpoint_returns_the_full_contracted_body`. Only gap = shared not-run-against-live-Postgres (SQLite tests). Spec: [docs/modules/M20-dashboard.md](docs/modules/M20-dashboard.md), plan: [docs/modules/M20-dashboard-plan.md](docs/modules/M20-dashboard-plan.md)
- [ ] `T206b` **[A1]** Fix: SQLAlchemy `Enum(...)` columns lack `values_callable`, so they persist the Python enum's **`.name`** (e.g. `'SENT'`, `'ACCEPTED'`) while the matching Postgres enum type declares **lowercase labels** (`'sent'`, `'accepted'`, per `infra/db/migrations/`) — every `status IN (...)`/equality filter against a live database will silently match nothing. Service-wide, not quote-service-specific: audit every `Enum(...)` column across all services (auth, customer, pricebook, quote, proposal, analytics) and add `values_callable=lambda e: [m.value for m in e]` (or equivalent) wherever needed. Predates T206; invisible under the SQLite test harness (degrades `Enum` to a VARCHAR + CHECK, so no test currently catches it). **Blocks any live-Postgres verification pass from being trustworthy** — fix before T206's or T207's Postgres-integration gaps are closed. — _deps: none_ · found during T206's final whole-branch review
- [x] `T207` **[A3-Low]** M25 Unit + integration test suites for Phase 1 services — _deps: T104, T105, T106_ ✅ **CTO-audited**: RLS suite (R1) + master runner genuinely good, verified by running; DTO-placement (R2) was backwards (domain→interface dependency + dead code) — **fixed directly by CTO**, all 4 services now ruff/mypy/pytest clean ([audit](docs/handoffs/T002b-T110-T207-audit.md))

## 📱 PHASE 3 — Mobile · Payments · Intelligence · Launch (Weeks 9–12)

- [x] `T301` **[A4 / A3-Assisted]** M13 Flutter app: auth, CRM, quote builder, offline shell — _deps: T104, T106, T108_ ✅ **CTO-audited & SIGNED OFF as a UI-shell milestone (2026-07-25)** — Clean Architecture Flutter app in `apps/mobile` (Flutter 3.41 / Riverpod / GoRouter / field dark theme): auth/CRM/pricebook/quote-builder/offline-banner screens + a real, tested quote calculation engine. Independently re-ran the toolchain: **`flutter analyze` 0 errors** (7 cosmetic `withOpacity` info-deprecations), **`flutter test` 5/5** (calc engine + money/bps + widget). ⚠️ **Scope limit — it's a UI prototype, not yet backend-integrated:** `ApiClient` is present but **unused (dead code)**, screens render **mock data**, **no live JWT auth flow**, and the default gateway port is wrong (`8080` vs `8000`). Full verdict: [docs/handoffs/T301-flutter-mobile-app-handoff.md](docs/handoffs/T301-flutter-mobile-app-handoff.md#-cto-audit-verdict--agent-1-2026-07-25). Follow-up (real gateway wiring + auth) belongs to the next mobile increment alongside T302.
- [ ] `T301b` **[A4]** M13 Mobile backend integration: wire the dead `ApiClient` into the screens, add a real JWT auth flow (login → token → gateway), replace mock data with live gateway calls, fix the default port (8080→8000) — _deps: T301_ · from the T301 CTO audit
- [ ] `T302` **[A4]** M14 Offline sync engine (local DB + conflict resolution + queue) — _deps: T301_
- [ ] `T303` **[A4]** M11 Payments: Stripe/Square, deposits, installments, invoices — _deps: T203_
- [ ] `T304` **[A3-High]** M18 AI Vision: photo→equipment detection→material list — _deps: T202_
- [ ] `T305` **[A3-High]** M19 AI OCR: supplier invoices/blueprints/handwriting→structured — _deps: T202_
- [ ] `T306` **[A3-High]** M17 AI Sales Coach: upsell/warranty/cross-sell suggestions — _deps: T202_
- [x] `T307` **[A3-Med]** M21 Analytics: close rate, forecast, LTV, profit by trade — _deps: T206_ ✅ Clean Architecture FastAPI service in `services/analytics-service` with Repository Pattern protocol, header-trust tenancy (`x-tenant-id`), analytics overview, trade breakdowns, customer LTV leaderboards, event ingestion endpoint (`/v1/analytics/events/ingest`), API Gateway route `/v1/analytics`, 9/9 pytest tests, ruff clean, mypy clean, and strict RLS tenant isolation suite.
- [ ] `T308` **[A3-Med]** M23 Integrations: QuickBooks/Xero + Zapier + REST API — _deps: T303_
- [ ] `T309` **[A4]** M24 Production infra: Railway/Fly.io + Cloudflare + monitoring — _deps: T004_
- [ ] `T310` **[A1]** M27 Security review + OWASP pass + pen-test checklist → launch gate — _deps: all Phase 3_

---

## ➡️ Check for Next Task

> **Current unblocked, ready-to-start tasks** (update this list as you complete work):

| Ready now       | Agent | Blocked-until                                               |
| --------------- | ----- | ----------------------------------------------------------- |
| `T201`, `T202`  | A1    | T106 done ✅ → AI Quote Assistant / Copilot can start       |
| `T206b`         | A1    | no deps → enum `values_callable` fix, ready now             |
| `T301`          | A4    | T104 + T106 + T108 done ✅ → Flutter app can start now      |
| Everything else | —     | waiting on Phase 1/2 chain                                  |

> ✅ **Phase 1 is fully complete** (12/12 — auth, gateway, CRM, pricebook, quote engine, PDF engine,
> web shell, quote builder UI, infra, seed data, test suites, all reconciliation/audits closed). See
> [T002b/T110/T207 audit](docs/handoffs/T002b-T110-T207-audit.md) and
> [T106 audit](docs/handoffs/T106-quote-service-audit.md). All 5 backend services are ruff/mypy/
> pytest clean and pass `scripts/check_conventions.py`; the web app is typecheck-clean with a green
> `next build` across all 11 routes.
>
> The T109 web-app gap (the "gateway unreachable → error banner" path unconfirmed in a real browser)
> is now **closed** — it was verified in a real browser during T206; see
> [apps/web/README.md](apps/web/README.md#definition-of-done) for the evidence.
>
> Four honest gaps remain, tracked not blocking:
> (1) no service has been run live against Postgres yet — T002b proved the infra/migrations, not
> per-service runtime — so `tests/integration/test_postgres_rls.py` has never executed its real
> assertions (only its skip-path is verified); this now also covers the T206 summary endpoint, whose
> happy path (real KPI numbers over real rows) has likewise never run against a live database.
> **Do not close this gap without first landing `T206b`** — SQLAlchemy's `Enum(...)` columns persist
> the Python enum's `.name` (`'SENT'`) against a Postgres type declaring lowercase labels (`'sent'`),
> so any live-Postgres pass run before that fix will pass a broken status filter silently;
> (2) `run_all_tests.py` doesn't yet include the web app's test/typecheck/build in its sweep;
> (3) the T206 summary endpoint's happy path is untestable without a live database in the first
> place — the route calls `tenant_session()` directly with no override seam, so there is no test
> asserting the 200 response body; only the SQLite-backed unit tests (`resolve_range` /
> `summarize_quotes`) and the gateway-down error path are verified;
> (4) T203's `resolve_proposal_tenant` **`SECURITY DEFINER`** Postgres function — the one backing the
> public, unauthenticated `GET /v1/proposals/{id}/view` route — has never run against real Postgres
> either, and neither has the full proposal create→send→view happy path; only SQLite-backed
> unit/route tests and a `FakeTenantResolver` seam have exercised the surrounding logic. This also
> **blocks on `T206b`** before any live-Postgres pass over it can be trusted. (T203's own
> `proposal_status` enum is not itself part of the `T206b` fix — confirmed in
> `services/proposal-service/app/infrastructure/models.py`, it already declares
> `values_callable=lambda enum_cls: [member.value for member in enum_cls]` correctly from the start —
> but `T206b` remains open service-wide and still blocks trusting a live-Postgres pass over any of
> auth/customer/pricebook/quote/proposal/analytics until it lands.) No live browser verification of
> the `/view` link (with no session/token present) has been done either, for the same reason — it
> requires the full gateway + proposal-service + Postgres stack running together, which this
> environment cannot provide (no Docker daemon, nothing on port 5432).

**Rule:** a task is "ready" when every dep is `[x]`. When you finish a task, scan its dependents and move any newly-unblocked ones into this table.

---

## 📊 Module Completion Rollup

| Phase     | Total  | Done   | In Progress | %       |
| --------- | ------ | ------ | ----------- | ------- |
| Phase 0   | 6      | 6      | 0           | 100%    |
| Phase 1   | 12     | 12     | 0           | 100%    |
| Phase 2   | 8      | 3      | 0           | 38%     |
| Phase 3   | 11     | 2      | 0           | 18%     |
| **Total** | **37** | **23** | **0**       | **62%** |

_Keep this rollup in sync with the CSV tracker after each completed task._
