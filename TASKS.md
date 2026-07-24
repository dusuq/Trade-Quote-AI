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
- [ ] `T002b` **[A3 · Antigravity]** **Live smoke test of the dev stack on GCP** (local Docker Desktop unavailable) — _deps: T002_ → see [handoff](docs/handoffs/T002b-smoke-test-GCP.md)
- [x] `T003` **[A1]** Global domain-event schema + naming conventions → `packages/types` + `docs/03-DOMAIN-EVENTS.md` — _deps: T000_ ✅ verified (typechecks + builds)
- [x] `T004` **[A4]** GitHub Actions CI skeleton (JS/TS + Python + Flutter lanes) — _deps: T001_ ✅ verified (all 5 stages green locally)

## 🔐 PHASE 1 — MVP Core (Weeks 1–4)

- [x] `T101` **[A1]** M1 Auth-service: tenants, users, RBAC, JWT, MFA (FastAPI, Clean Arch) — _deps: T002_ ✅ security core 9/9 tests + ruff clean; ⏳ live DB integration under T002b
- [x] `T102` **[A1]** M3 DB schema v1 (tenant/user/customer/property/pricebook/quote) + RLS migrations — _deps: T002_ ✅ 5 ordered migrations, structurally valid; ⏳ live apply under T002b
- [x] `T103` **[A1]** M2 API Gateway routing + auth middleware + rate limiting (Fastify) — _deps: T101_ ✅ 14/14 tests + typecheck/build clean; live integration natural once T002b is up
- [x] `T104` **[A2]** M4 Customer CRM service: CRUD, properties, contacts, notes, tags, timeline (FastAPI + Repository Pattern) — _deps: T102, T103_ ✅ 21/21 tests + ruff/mypy clean; gateway route wired; ⏳ live DB under T002b
- [x] `T105` **[A2]** M6 Pricebook service: materials/labor/equipment, regional pricing, import — _deps: T102, T103_ ✅ 5/5 unit+integration tests + Clean Arch + regional pricing + CSV import — ⚠️ conditional sign-off pending T105b
- [ ] `T105b` **[A3 · Antigravity]** Reconcile pricebook to gateway auth pattern (remove JWT decode → trust `x-tenant-id`) — _deps: T105_ → see [handoff](docs/handoffs/T105b-pricebook-auth-reconciliation.md) · **CI red until fixed** (convention guard)
- [ ] `T105c` **[A1]** Audit Agent 3's T105b fix on completion report (guard + ruff/mypy/pytest + gateway→pricebook header path) → final T105 sign-off — _deps: T105b_
- [x] `T106` **[A2]** M7 Quote engine: line items, tax, margin/markup, totals, versioning — _deps: T105_ ✅ 5/5 unit+integration tests + Clean Arch + calculation engine + versioning + domain events
- [ ] `T107` **[A4]** M9 PDF engine: branded proposal PDF, QR, signature block — _deps: T106_
- [ ] `T108` **[A2]** M12 Web app shell + design system (Tailwind + shadcn/ui) + auth flows — _deps: T103_
- [ ] `T109` **[A2]** M12 Quote builder UI (web) wired to quote-service — _deps: T106, T108_
- [ ] `T110` **[A3-Low]** M26 Seed data + fixture generator (sample pricebooks per trade) — _deps: T105_

## 🤖 PHASE 2 — AI + Delivery (Weeks 5–8)

- [ ] `T201` **[A1]** M15 AI Quote Assistant: voice→text→structured scope→line items — _deps: T106_
- [ ] `T202` **[A1]** M16 AI Copilot: pricing/margin/missing-items/rewrite endpoints — _deps: T106, T201_
- [ ] `T203` **[A2]** M8 Proposal Builder: templates, cover page, branding, terms, warranty — _deps: T107_
- [ ] `T204` **[A4]** M10 E-Signature + audit trail (IP, timestamp, hash chain) — _deps: T203_
- [ ] `T205` **[A4]** M22 Notifications: email + SMS delivery of quotes/proposals — _deps: T203_
- [ ] `T206` **[A2]** M20 Dashboard: quotes today/pending/accepted/revenue/conversion — _deps: T106_
- [ ] `T207` **[A3-Low]** M25 Unit + integration test suites for Phase 1 services — _deps: T104, T105, T106_

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

| Ready now       | Agent            | Blocked-until                                              |
| --------------- | ---------------- | ---------------------------------------------------------- |
| `T002b`         | A3 · Antigravity | — ready now (run stack on GCP; needs GCP account)          |
| `T107`          | A4               | T106 done ✅ → PDF engine can build now                    |
| `T108`          | A2               | T103 done ✅ → web app shell can build against gateway now |
| Everything else | —                | waiting on Phase 1 chain / T002b live DB                   |

> ✅ **T101–T105 authored & verified** (parallel: A1 built T101–T104, A3/Antigravity built T105).
> Auth-service (9/9), 5 RLS migrations, API Gateway (14/14; now routes /v1/auth + /v1/customers +
> /v1/pricebook), Customer CRM (21/21: Repository Pattern, tenant isolation, pagination, timeline),
> and Pricebook (5/5: regional pricing + CSV import) are done. The one live gate remaining is
> **T002b — Agent 3 runs the stack + `run-migrations.sh` on GCP**; that turns every ⏳
> live-integration item green and unblocks real end-to-end testing.
>
> ⚠️ **CTO review note (for reconciliation):** the pricebook-service (A3) decodes JWTs itself,
> whereas auth/customer/gateway use the pattern "gateway verifies JWT → services trust the
> `x-tenant-id` header." Worth aligning on one auth pattern across services (tracked separately).

**Rule:** a task is "ready" when every dep is `[x]`. When you finish a task, scan its dependents and move any newly-unblocked ones into this table.

---

## 📊 Module Completion Rollup

| Phase     | Total  | Done   | In Progress | %       |
| --------- | ------ | ------ | ----------- | ------- |
| Phase 0   | 6      | 5      | 0           | 83%     |
| Phase 1   | 10     | 5      | 0           | 50%     |
| Phase 2   | 7      | 0      | 0           | 0%      |
| Phase 3   | 10     | 0      | 0           | 0%      |
| **Total** | **33** | **10** | **0**       | **30%** |

_Keep this rollup in sync with the CSV tracker after each completed task._
