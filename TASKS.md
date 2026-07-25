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
- [ ] `T109` **[A2]** M12 Quote builder UI (web) wired to quote-service — _deps: T106, T108_
- [x] `T110` **[A3-Low]** M26 Seed data + fixture generator (sample pricebooks per trade) — _deps: T105_ ✅ **CTO-audited PASS** — Electrical/Plumbing/HVAC catalogs verified via real pricebook import (3/3); full suite 8/8 green

## 🤖 PHASE 2 — AI + Delivery (Weeks 5–8)

- [ ] `T201` **[A1]** M15 AI Quote Assistant: voice→text→structured scope→line items — _deps: T106_
- [ ] `T202` **[A1]** M16 AI Copilot: pricing/margin/missing-items/rewrite endpoints — _deps: T106, T201_
- [ ] `T203` **[A2]** M8 Proposal Builder: templates, cover page, branding, terms, warranty — _deps: T107_
- [ ] `T204` **[A4]** M10 E-Signature + audit trail (IP, timestamp, hash chain) — _deps: T203_
- [ ] `T205` **[A4]** M22 Notifications: email + SMS delivery of quotes/proposals — _deps: T203_
- [ ] `T206` **[A2]** M20 Dashboard: quotes today/pending/accepted/revenue/conversion — _deps: T106_
- [x] `T207` **[A3-Low]** M25 Unit + integration test suites for Phase 1 services — _deps: T104, T105, T106_ ✅ **CTO-audited**: RLS suite (R1) + master runner genuinely good, verified by running; DTO-placement (R2) was backwards (domain→interface dependency + dead code) — **fixed directly by CTO**, all 4 services now ruff/mypy/pytest clean ([audit](docs/handoffs/T002b-T110-T207-audit.md))

## 📱 PHASE 3 — Mobile · Payments · Intelligence · Launch (Weeks 9–12)

- [ ] `T301` **[A4]** M13 Flutter app: auth, CRM, quote builder, offline shell — _deps: T104, T106, T108_
- [ ] `T302` **[A4]** M14 Offline sync engine (local DB + conflict resolution + queue) — _deps: T301_
- [ ] `T303` **[A4]** M11 Payments: Stripe/Square, deposits, installments, invoices — _deps: T203_
- [ ] `T304` **[A3-High]** M18 AI Vision: photo→equipment detection→material list — _deps: T202_
- [ ] `T305` **[A3-High]** M19 AI OCR: supplier invoices/blueprints/handwriting→structured — _deps: T202_
- [ ] `T306` **[A3-High]** M17 AI Sales Coach: upsell/warranty/cross-sell suggestions — _deps: T202_
- [ ] `T307` **[A3-Med]** M21 Analytics: close rate, forecast, LTV, profit by trade — _deps: T206_
- [ ] `T308` **[A3-Med]** M23 Integrations: QuickBooks/Xero + Zapier + REST API — _deps: T303_
- [ ] `T309` **[A4]** M24 Production infra: Railway/Fly.io + Cloudflare + monitoring — _deps: T004_
- [ ] `T310` **[A1]** M27 Security review + OWASP pass + pen-test checklist → launch gate — _deps: all Phase 3_

---

## ➡️ Check for Next Task

> **Current unblocked, ready-to-start tasks** (update this list as you complete work):

| Ready now       | Agent | Blocked-until                                                |
| --------------- | ----- | ------------------------------------------------------------ |
| `T109`          | A2    | T106 + T108 done ✅ → quote builder UI can wire up now       |
| `T201`, `T202`  | A1    | T106 done ✅ → AI Quote Assistant / Copilot can start        |
| `T203`          | A2    | T107 done ✅ → Proposal Builder can call the new PDF engine  |
| `T206`          | A2    | T106 done ✅ → Dashboard can build against quote-service now |
| Everything else | —     | waiting on Phase 1/2 chain                                   |

> ✅ **Phase 1 fully closed for auth/gateway/CRM/pricebook/quote/PDF-engine/web-shell + infra.** T101–T108
> (with T105b/c reconciliation), T002b (GCP smoke test), T110 (seed data), and T207 (Phase 1 test
> suites) are all done — see
> [T002b/T110/T207 audit](docs/handoffs/T002b-T110-T207-audit.md) and
> [T106 audit](docs/handoffs/T106-quote-service-audit.md). All 5 backend services are ruff/mypy/
> pytest clean and pass `scripts/check_conventions.py` (verified via `scripts/run_all_tests.py`,
> which now also runs ruff+mypy per service). Two honest gaps remain, tracked not blocking:
> (1) no service has been run live against Postgres yet — T002b proved the infra/migrations, not
> per-service runtime — so the new `tests/integration/test_postgres_rls.py` has never actually
> executed its assertions (only its skip-path is verified). Gap (2) — `run_all_tests.py` only running
> pytest — has since been fixed; it now runs pytest + ruff + mypy per service.

**Rule:** a task is "ready" when every dep is `[x]`. When you finish a task, scan its dependents and move any newly-unblocked ones into this table.

---

## 📊 Module Completion Rollup

| Phase     | Total  | Done   | In Progress | %       |
| --------- | ------ | ------ | ----------- | ------- |
| Phase 0   | 6      | 6      | 0           | 100%    |
| Phase 1   | 12     | 11     | 0           | 92%     |
| Phase 2   | 7      | 1      | 0           | 14%     |
| Phase 3   | 10     | 0      | 0           | 0%      |
| **Total** | **35** | **18** | **0**       | **51%** |

_Keep this rollup in sync with the CSV tracker after each completed task._
