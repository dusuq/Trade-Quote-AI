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

- [x] `T201` **[A1]** M15 AI Quote Assistant: voice→text→structured scope→line items — _deps: T106_ ✅ **DONE (2026-07-28)** — new `services/ai-service` (port 8008, gateway `/v1/ai`). Voice and text entry points converge on one pipeline: transcribe → extract structured scope (`claude-opus-5` with **structured outputs**, so no "reply with JSON only" pleading and no brace-counting parser) → match against the tenant's pricebook → create a draft quote. **120/120 ai-service tests** (money/markup mapping, match scoring, audio validation, cost math, scope parsing, both use cases, HTTP retry semantics, routes, tenant isolation, usage tracking), ruff/mypy clean; **26/26 gateway tests** (up from 25); all 8 backend services green; `check_conventions.py` OK. **Corrected two errors in the plan:** it specified `claude-sonnet-4-20250514` (superseded) and `temperature: 0.1` — current models **reject** `temperature` with a 400, and the constrained output schema serves the determinism intent instead. **Pricing deliberately stays in quote-service** — ai-service sends `unit_cost_minor` + `markup_bps` and never computes a price, since a second implementation of that arithmetic is a second thing that can drift; a matched item's own `default_markup_bps` beats the request default. Unmatched items become $0 lines rather than being dropped or guessed at. Also wrote **[ADR-0003](docs/adr/ADR-0003-sync-service-to-service-http.md)** (sync service-to-service HTTP: allowed on the critical path, forbidden for side effects — the rule the T307b audit asked for), with a shared client that never replays a POST after a timeout. Spec: [M15 spec](docs/modules/M15-ai-quote-assistant.md); plan: [M15 plan](docs/modules/M15-ai-quote-assistant-plan.md). ⚠️ **Scope limit: no web UI** — tracked as **T201b**; no idempotency key yet (see spec §6).
- [ ] `T201b` **[A2]** M15 AI Quote Assistant web UI: voice-record button + transcript review on the quote builder, "describe the job" text entry, extracted-scope review before the quote is created (showing which lines matched the pricebook and which need pricing), and a scope-writer action on the proposal editor — _deps: T201_ · from T201's own scope limit; backend is complete and gateway-reachable, nothing drives it yet
- [ ] `T202` **[A1]** M16 AI Copilot: pricing/margin/missing-items/rewrite endpoints — _deps: T106, T201_
- [x] `T203` **[A2]** M8 Proposal Builder: templates, cover page, branding, terms, warranty — _deps: T107_ ✅ **CTO-audited & SIGNED OFF (2026-07-28)** — `proposal_template`/`proposal`/`proposal_version` persistence on top of T107's PDF engine — template CRUD, create/send/view lifecycle, and the public unauthenticated `GET /v1/proposals/{id}/view` link. Audit re-ran everything green, counts actually a touch higher than claimed: **32/32 proposal-service + 20/20 gateway + 71/71 web tests**, ruff/mypy/typecheck/`next build` (14/14 routes) clean, `check_conventions.py` OK. Confirmed the gateway now strips client-supplied `x-tenant-id`/`x-user-id`/`x-user-roles` unconditionally before the `/view` route (the one intentionally public, unauthenticated route) reaches the upstream, and that `resolve_proposal_tenant` (`SECURITY DEFINER`) returns only `tenant_id` — nothing else. **Separately from this task's own scope, found and fixed an app-wide bug in `apps/api-gateway`'s `registerServiceProxy`: its `${prefix}/*` wildcard mount never matched the bare prefix with no trailing segment, so every bare `GET`/`POST` to a collection endpoint (`GET /v1/quotes`, `POST /v1/customers`, etc. — not just the new proposal routes) 404'd through the real gateway, invisible until now because no prior task ran the full stack live and no gateway test exercised a bare-prefix request.** Fixed by registering the handler at both the bare prefix and the wildcard, with regression tests (`test/server.test.ts`). Only gap = the `SECURITY DEFINER` function and the full create→send→view happy path have never run against live Postgres (no Docker locally) — folded into **T311** below. Spec: [docs/modules/M8-proposal-builder.md](docs/modules/M8-proposal-builder.md); plan: [docs/modules/M8-proposal-builder-plan.md](docs/modules/M8-proposal-builder-plan.md); full audit: [T203 audit](docs/handoffs/T203-proposal-builder-audit.md).
- [x] `T204` **[A1]** M10 E-Signature + audit trail (IP, timestamp, hash chain) — _deps: T203_ ✅ **DONE (2026-07-28)** — built by Agent 1 (CTO) at founder direction; board lane was A4. New `services/esign-service` (port 8007) — `esign` is a declared bounded context in `packages/types`, so this is its own service, not an extension of proposal-service. **Tamper-evident hash-chained audit trail** (`app/domain/hash_chain.py`): every state change appends an entry committing to the previous entry's hash, so mutation, deletion, reordering, and splicing an entry in from another signature request all break verification and report the exact sequence number. Signature is bound to the exact document (`document_sha256` captured at request time, re-asserted at signing); consent-to-transact-electronically and intent-to-sign are both required and recorded (ESIGN/UETA). Public signing links use `secrets.token_urlsafe(32)` capability tokens, independently voidable/expirable — deliberately *not* the row id, unlike T203's `/view` link. **63/63 esign tests** (incl. 13 hash-chain tamper cases + a DB-round-trip regression guard), ruff/mypy clean; **25/25 gateway tests** (up from 20 — added public-route-pattern and forwarded-IP coverage); all 7 backend services + 71/71 web tests still green; `check_conventions.py` OK. Also hardened the gateway: it now **overwrites** client-supplied `x-forwarded-for` with the real peer address, so a signer can't forge the IP written into a legal audit record. Migration `0008_esign.sql` adds RLS on all three tables plus an **append-only trigger** on `signature_audit_event` (UPDATE/DELETE raise) — the operational control backing the chain's documented limit. Spec: [docs/modules/M10-esignature.md](docs/modules/M10-esignature.md). ⚠️ **Scope limit: no web UI** — tracked as **T204b**, same standard applied to T307b.
- [ ] `T204b` **[A2]** M10 E-Signature web UI: request-signature action on a proposal, signing-request list/detail with the audit trail + verification badge, and the public customer-facing signing page (consent + intent checkboxes, typed signature) — _deps: T204_ · from T204's own scope limit; backend is complete and gateway-reachable, nothing drives it yet
- [ ] `T205` **[A4]** M22 Notifications: email + SMS delivery of quotes/proposals — _deps: T203_
- [x] `T206` **[A2]** M20 Dashboard: quotes today/pending/accepted/revenue/conversion — _deps: T106_ ✅ **CTO-audited & SIGNED OFF (2026-07-25, reconfirmed 2026-07-28)** — `GET /v1/quotes/summary` read model (tz-aware boundary math via client-supplied IANA zone) + live `/dashboard` page. Audit re-ran green: **29/29 quote-service + 71/71 web tests** (web suite grew with T203's proposal tests; dashboard's own 14 tests unaffected), ruff/mypy/typecheck/`next build` clean, `check_conventions.py` OK — no regressions since the original sign-off. Route-ordering trap (`/summary` before `/{quote_id}`) handled **with a regression test**; full 200 body pinned by `test_summary_endpoint_returns_the_full_contracted_body` via the `api_session` monkeypatch seam in `tests/conftest.py` (there is no `Depends` to override, so that's the actual seam — see corrected note below). Only gap = shared not-run-against-live-Postgres (SQLite tests) — folded into **T311**. Spec: [docs/modules/M20-dashboard.md](docs/modules/M20-dashboard.md), plan: [docs/modules/M20-dashboard-plan.md](docs/modules/M20-dashboard-plan.md)
- [x] `T206b` **[A3 · Antigravity]** Fix SQLAlchemy `Enum(...)` columns lack `values_callable` — _deps: none_ ✅ **COMPLETED by Agent 3, CTO-verified 2026-07-28** — Added `values_callable=lambda e: [m.value for m in e]` to `services/quote-service/app/domain/models.py` (`QuoteStatus`, `QuoteCreatedVia`, `ItemKind`) and `services/pricebook-service/app/domain/models.py` (`ItemKind`), plus `test_enum_values_callable.py` in both services asserting the callable returns lower-case values matching the Postgres enum labels. Independently re-ran: **quote-service 32/32 pytest + ruff + mypy clean; pricebook-service 9/9 pytest + ruff + mypy clean.** Unblocks **T311**.
- [x] `T207` **[A3-Low]** M25 Unit + integration test suites for Phase 1 services — _deps: T104, T105, T106_ ✅ **CTO-audited**: RLS suite (R1) + master runner genuinely good, verified by running; DTO-placement (R2) was backwards (domain→interface dependency + dead code) — **fixed directly by CTO**, all 4 services now ruff/mypy/pytest clean ([audit](docs/handoffs/T002b-T110-T207-audit.md))

## 📱 PHASE 3 — Mobile · Payments · Intelligence · Launch (Weeks 9–12)

- [x] `T301` **[A4 / A3-Assisted]** M13 Flutter app: auth, CRM, quote builder, offline shell — _deps: T104, T106, T108_ ✅ **CTO-audited & SIGNED OFF as a UI-shell milestone (2026-07-25)** — Clean Architecture Flutter app in `apps/mobile` (Flutter 3.41 / Riverpod / GoRouter / field dark theme): auth/CRM/pricebook/quote-builder/offline-banner screens + a real, tested quote calculation engine. Independently re-ran the toolchain: **`flutter analyze` 0 errors** (7 cosmetic `withOpacity` info-deprecations), **`flutter test` 5/5** (calc engine + money/bps + widget). ⚠️ **Scope limit — it's a UI prototype, not yet backend-integrated:** `ApiClient` is present but **unused (dead code)**, screens render **mock data**, **no live JWT auth flow**, and the default gateway port is wrong (`8080` vs `8000`). Full verdict: [docs/handoffs/T301-flutter-mobile-app-handoff.md](docs/handoffs/T301-flutter-mobile-app-handoff.md#-cto-audit-verdict--agent-1-2026-07-25). Follow-up (real gateway wiring + auth) belongs to the next mobile increment alongside T302.
- [ ] `T301b` **[A4]** M13 Mobile backend integration: wire the dead `ApiClient` into the screens, add a real JWT auth flow (login → token → gateway), replace mock data with live gateway calls, fix the default port (8080→8000) — _deps: T301_ · from the T301 CTO audit
- [ ] `T302` **[A4]** M14 Offline sync engine (local DB + conflict resolution + queue) — _deps: T301_
- [ ] `T303` **[A4]** M11 Payments: Stripe/Square, deposits, installments, invoices — _deps: T203_
- [ ] `T304` **[A3-High]** M18 AI Vision: photo→equipment detection→material list — _deps: T202_
- [ ] `T305` **[A3-High]** M19 AI OCR: supplier invoices/blueprints/handwriting→structured — _deps: T202_
- [ ] `T306` **[A3-High]** M17 AI Sales Coach: upsell/warranty/cross-sell suggestions — _deps: T202_
- [x] `T307` **[A3-Med]** M21 Analytics: close rate, forecast, LTV, profit by trade — _deps: T206_ ⚠️ **CTO-audited 2026-07-28 — signed off only as a calculation-engine prototype, NOT feature-complete M21.** Clean Architecture FastAPI service in `services/analytics-service` with a genuine `Protocol`-based repository, header-trust tenancy (`x-tenant-id`), analytics overview/trade-breakdown/LTV calculation logic, an event-ingestion endpoint, API Gateway route `/v1/analytics` wired, 9/9 pytest tests, ruff/mypy clean — all confirmed accurate. **But:** the route layer runs entirely on an **in-memory** repository (`shared_repo`, a process-local Python list) — the "production" `SqlAlchemyAnalyticsRepository`/`AnalyticsEventORM` are dead code, never constructed, and would fail anyway since **no migration creates the `analytics_events` table**; there is **no RLS policy** anywhere for it, so "strict RLS tenant isolation suite" was a mischaracterization — the test genuinely proves tenant isolation, but at the application level against the in-memory repo, not at the database level; and **nothing in quote-service or proposal-service ever calls the ingest endpoint**, so in any real deployment this would show empty data forever. No web UI exists either. Follow-up (real persistence + RLS + event-producer wiring + web page) tracked as **T307b**. Full audit: [T307 audit](docs/handoffs/T307-analytics-audit.md).
- [ ] `T308` **[A3-Med]** M23 Integrations: QuickBooks/Xero + Zapier + REST API — _deps: T303_
- [ ] `T309` **[A4]** M24 Production infra: Railway/Fly.io + Cloudflare + monitoring — _deps: T004_
- [ ] `T310` **[A1]** M27 Security review + OWASP pass + pen-test checklist → launch gate — _deps: all Phase 3_
- [~] `T307b` **[A3]** M21 Analytics — make it real — _deps: T307_ ⚠️ **REWORK REQUIRED — CTO audit 2026-07-28 did not accept this as done** (was briefly marked complete; corrected same day). **Genuinely landed and good:** `infra/db/migrations/0007_analytics.sql` with the `analytics_events` table + RLS policy (correctly using the reserved number, no collision with T204's `0008`), routes swapped to a per-request `tenant_session`-scoped `SqlAlchemyAnalyticsRepository` (the in-memory singleton flagged in the T307 audit is gone), and a real `/analytics` web page that compiles (`next build` 15/15). **Blocking defects, all in `quote-service`'s `_emit_analytics_event`:** (1) the best-effort guard catches `httpx.HTTPError`, but `httpx.InvalidURL` is *not* a subclass — **verified at runtime** — so a malformed `ANALYTICS_SERVICE_URL` 500s quote create/send/accept/reject; (2) the blocking `httpx.post` runs **inside the open DB transaction**, holding a pooled connection for its 2s timeout; (3) emitted event names (`quote.created`…) don't match the canonical registry (`quote.quote.created`, `quote.estimate.accepted`…) — a **conventions §4 violation** the guard can't currently see; (4) `trade` is derived from the free-text quote title, so M21's headline "profit by trade" breakdown degenerates to one bucket per quote; (5) `customer_name` is fabricated as `Customer 3f2a1b9c`, making the LTV leaderboard meaningless; (6) non-atomic, and it introduces the first sync service-to-service HTTP call — which M8's spec (D2) explicitly declined to introduce without a shared client/retry pattern — with no ADR. Code left **uncommitted in the working tree** for rework; nothing discarded. Full findings + acceptance criteria: [T307b audit](docs/handoffs/T307b-analytics-wiring-audit.md).
- [x] `T311` **[A3 · Antigravity]** M25 Live-Postgres verification pass — _deps: T206b_ ✅ **COMPLETED & VERIFIED (2026-07-28)** — Verified full PostgreSQL RLS test suite against live GCP PostgreSQL (`pgvector/pgvector:pg16`), including T203 `resolve_proposal_tenant` (`SECURITY DEFINER` function for public `/view` route), T206/T206b status enum values_callable lower-case filtering against live rows, and T307b `analytics_events` RLS isolation. All 6 integration tests passed 100%. Evidence report published to [T311 results](docs/handoffs/T311-live-postgres-verification-results.md). Disposable GCP VM and firewall rule torn down.

---

## ➡️ Check for Next Task

> **Current unblocked, ready-to-start tasks** (update this list as you complete work):

| Ready now       | Agent | Blocked-until                                               |
| --------------- | ----- | ----------------------------------------------------------- |
| `T202`          | A1    | T201 done ✅ → AI Copilot can start (shares ai-service's LLM infra) |
| `T201b`         | A2    | T201 done ✅ → AI Quote Assistant web UI (backend complete, nothing drives it yet) |
| `T205`, `T303`  | A4    | T203 done ✅ → Notifications / Payments can start             |
| `T204b`         | A2    | T204 done ✅ → E-Signature web UI (backend complete, nothing drives it yet) |
| `T307b`         | A3    | ⚠️ **rework** — see [T307b audit](docs/handoffs/T307b-analytics-wiring-audit.md); code is in the working tree, uncommitted |
| `T301b`         | A4    | T301 done ✅ → mobile backend integration can start          |
| Everything else | —     | waiting on Phase 2/3 chain                                  |

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
> **Correction (2026-07-28):** the bullet below previously claimed the T206 summary route "calls
> `tenant_session()` directly with no override seam, so there is no test asserting the 200 response
> body." That was wrong and has been removed — `services/quote-service/tests/conftest.py`'s
> `api_session` fixture monkeypatches `app.interface.routes.tenant_session` (the actual seam, since
> there's no FastAPI `Depends` to override), and
> `test_summary_endpoint_returns_the_full_contracted_body` does assert the full 200 body through it.
> The real, remaining gap was never "untested" — it's "never tested against **live Postgres**,"
> which is a different and narrower claim; see below.
>
> Three honest gaps remain, none blocking, all now tracked under **T311** (assigned to Agent 3 —
> see rationale there): no service has been run live against Postgres yet (T002b proved the
> infra/migrations, not per-service runtime), so (1) `tests/integration/test_postgres_rls.py` has
> never executed its real assertions (only its skip-path is verified); (2) T206's summary endpoint's
> happy path (real KPI numbers over real seeded rows) has only ever run against the SQLite fixture,
> never a live database; (3) T203's `resolve_proposal_tenant` **`SECURITY DEFINER`** Postgres
> function backing the public `GET /v1/proposals/{id}/view` route, and the full proposal
> create→send→view happy path, have likewise only run against SQLite-backed unit/route tests and a
> `FakeTenantResolver` seam. **All three block on `T206b` landing first** — SQLAlchemy's `Enum(...)`
> columns persist the Python enum's `.name` (`'SENT'`) against a Postgres type declaring lowercase
> labels (`'sent'`), so any live-Postgres pass run before that fix would pass a broken status filter
> silently. (T203's own `proposal_status` enum is not itself part of the `T206b` fix — confirmed in
> `services/proposal-service/app/infrastructure/models.py`, it already declares
> `values_callable=lambda enum_cls: [member.value for member in enum_cls]` correctly from the start;
> the two models still missing it are `quote-service`'s and `pricebook-service`'s.) Separately,
> `run_all_tests.py` still doesn't include the web app's test/typecheck/build in its sweep — a minor
> script gap, not Docker/Postgres-related, left open and not reassigned.
>
> **Docker/Postgres-dependent work goes to Agent 3 (Antigravity) going forward.** No other machine
> on this fleet has a Docker daemon or anything listening on 5432 — every live-Postgres claim so far
> (T002b) was proven by Agent 3 spinning up a disposable GCP VM, not locally. `T206b` and `T311` are
> reassigned/assigned on that basis.

**Rule:** a task is "ready" when every dep is `[x]`. When you finish a task, scan its dependents and move any newly-unblocked ones into this table.

---

## 📊 Module Completion Rollup

| Phase     | Total  | Done   | In Progress | %       |
| --------- | ------ | ------ | ----------- | ------- |
| Phase 0   | 6      | 6      | 0           | 100%    |
| Phase 1   | 12     | 12     | 0           | 100%    |
| Phase 2   | 10     | 6      | 0           | 60%     |
| Phase 3   | 13     | 3      | 1           | 23%     |
| **Total** | **41** | **27** | **1**       | **66%** |

_Keep this rollup in sync with the CSV tracker after each completed task._
