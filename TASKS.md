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
- [x] `T002b` **[A3 · Antigravity]** **Live smoke test of the dev stack on GCP** (local Docker Desktop unavailable) — _deps: T002_ ✅ 6/6 containers healthy + 5 DB extensions + MinIO bucket + 5 migrations verified live on GCP Compute Engine
- [x] `T003` **[A1]** Global domain-event schema + naming conventions → `packages/types` + `docs/03-DOMAIN-EVENTS.md` — _deps: T000_ ✅ verified (typechecks + builds)
- [x] `T004` **[A4]** GitHub Actions CI skeleton (JS/TS + Python + Flutter lanes) — _deps: T001_ ✅ verified (all 5 stages green locally)

## 🔐 PHASE 1 — MVP Core (Weeks 1–4)

- [x] `T101` **[A1]** M1 Auth-service: tenants, users, RBAC, JWT, MFA (FastAPI, Clean Arch) — _deps: T002_ ✅ security core 9/9 tests + ruff clean; ⏳ live DB integration under T002b
- [x] `T102` **[A1]** M3 DB schema v1 (tenant/user/customer/property/pricebook/quote) + RLS migrations — _deps: T002_ ✅ 5 ordered migrations, structurally valid; ⏳ live apply under T002b
- [x] `T103` **[A1]** M2 API Gateway routing + auth middleware + rate limiting (Fastify) — _deps: T101_ ✅ 14/14 tests + typecheck/build clean; live integration natural once T002b is up
- [x] `T104` **[A2]** M4 Customer CRM service: CRUD, properties, contacts, notes, tags, timeline (FastAPI + Repository Pattern) — _deps: T102, T103_ ✅ 21/21 tests + ruff/mypy clean; gateway route wired; ⏳ live DB under T002b
- [x] `T105` **[A3]** M6 Pricebook service: materials/labor/equipment, regional pricing, import — _deps: T102, T103_ ✅ 5/5 tests + Clean Arch + regional pricing + CSV import — **fully signed off (T105b+T105c complete)**
- [x] `T105b` **[A3 · Antigravity]** Reconcile pricebook to gateway auth pattern (remove JWT decode → trust `x-tenant-id`) — _deps: T105_ ✅ done by Agent 3; guard clean, no `jwt` anywhere
- [x] `T105c` **[A1]** CTO audit of T105b — _deps: T105b_ ✅ verified: 0 jwt refs, dead config removed, gateway wired, `check_conventions.py` green → **T105 signed off**
- [x] `T106` **[A3]** M7 Quote engine: line items, tax, margin/markup, totals, versioning — _deps: T105_ ✅ 5/5 tests + calc engine + versioning + domain events — **CTO-audited** ([report](docs/handoffs/T106-quote-service-audit.md)): conventions-clean; 3 non-blocking follow-ups (R1–R3)
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

| Ready now       | Agent            | Blocked-until                                               |
| --------------- | ---------------- | ----------------------------------------------------------- |
| `T002b`         | A3 · Antigravity | — **top priority**: run stack on GCP; needs GCP account     |
| `T110`          | A3 · Antigravity | T105 done ✅ → seed data/fixtures can build now             |
| `T207`          | A3 · Antigravity | T104, T105, T106 done ✅ → test suites for Phase 1 services |
| `T107`          | A4               | T106 done ✅ → PDF engine can build now                     |
| `T108`          | A2               | T103 done ✅ → web app shell can build against gateway now  |
| Everything else | —                | waiting on Phase 1 chain / T002b live DB                    |

> ✅ **T101–T106 (+ T105b/c reconciliation) all authored, verified, and CTO-audited.** Auth-service
> (9/9), 5 RLS migrations, API Gateway (14/14; routes /v1/auth, /v1/customers, /v1/pricebook,
> /v1/quotes), Customer CRM (21/21), Pricebook (5/5), and Quote Engine (5/5) are done — all on the
> single gateway-trust auth pattern (`scripts/check_conventions.py` green, see
> [docs/07-SERVICE-CONVENTIONS.md](docs/07-SERVICE-CONVENTIONS.md)). The one live gate remaining is
> **T002b — Agent 3 runs the stack + `run-migrations.sh` on GCP**; that turns every ⏳
> live-integration item green (including the real-RLS test noted in the
> [T106 audit](docs/handoffs/T106-quote-service-audit.md) R1) and unblocks true end-to-end testing.

**Rule:** a task is "ready" when every dep is `[x]`. When you finish a task, scan its dependents and move any newly-unblocked ones into this table.

---

## 📊 Module Completion Rollup

| Phase     | Total  | Done   | In Progress | %       |
| --------- | ------ | ------ | ----------- | ------- |
| Phase 0   | 6      | 5      | 0           | 83%     |
| Phase 1   | 12     | 8      | 0           | 67%     |
| Phase 2   | 7      | 0      | 0           | 0%      |
| Phase 3   | 10     | 0      | 0           | 0%      |
| **Total** | **35** | **13** | **0**       | **37%** |

_Keep this rollup in sync with the CSV tracker after each completed task._
