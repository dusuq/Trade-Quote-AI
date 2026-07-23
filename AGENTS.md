# 🤖 AGENTS.md — TradeQuote AI Development Fleet

This file defines the four AI development agents, their capabilities, and the modules each owns.
The CTO (Agent 1) assigns work here; every agent reads this before picking up a task in `TASKS.md`.

> **Assignment principle:** route each module to the agent whose model strengths best match the
> module's dominant skill (reasoning-heavy → Opus; fast full-stack → Sonnet 5; multimodal/vision/OCR/
> data → Gemini; mobile/infra/integrations breadth → Opus+Sonnet 4.6).

> **Agent 3 (Google Antigravity) cold-start:** paste
> [docs/handoffs/ANTIGRAVITY-AGENT3-ONBOARDING.md](docs/handoffs/ANTIGRAVITY-AGENT3-ONBOARDING.md)
> into a new Antigravity session — it's a self-contained folder tour, reading list, task queue, and
> GitHub setup/workflow guide.

---

## 🧠 Capability Matrix

| Agent                              | Model(s)                                                           | Superpowers                                                                                   | Best-fit work                                                                                       |
| ---------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Agent 1 — CTO Core**             | Claude Code **Opus 4.8** (`claude-opus-4-8`)                       | Deepest reasoning, system architecture, security, multi-step orchestration, AI systems design | Architecture, AI service, auth/RBAC/tenancy, DB schema, API-gateway contracts, code-review sign-off |
| **Agent 2 — Full-Stack**           | Claude Code **Sonnet 5** (`claude-sonnet-5`)                       | Fast, high-throughput full-stack coding, clean UI, CRUD/domain services                       | Web frontend + design system, CRM, quote engine, pricebook, proposal backend                        |
| **Agent 3 — Gemini / Antigravity** | Google Antigravity: **Gemini 3.5** & **3.6** (Low / Medium / High) | Multimodal (image+doc), long-context, data pipelines, cheap high-volume generation            | AI Vision, AI OCR, analytics pipelines, 3rd-party integrations, test generation, documentation      |
| **Agent 4 — Mobile & Platform**    | Claude Code **Opus + Sonnet 4.6**                                  | Broad engineering: mobile, offline sync, payments, infra, reliability                         | Flutter apps, offline sync engine, payments, notifications, DevOps/CI-CD/IaC                        |

### Gemini effort-tier routing (Agent 3)

| Tier       | Model                   | Use for                                                                            |
| ---------- | ----------------------- | ---------------------------------------------------------------------------------- |
| **Low**    | Gemini 3.5 / 3.6 Low    | Docs, boilerplate, unit-test scaffolds, changelog, data seed generation            |
| **Medium** | Gemini 3.5 / 3.6 Medium | Standard integration connectors, analytics queries, DTO mapping                    |
| **High**   | Gemini 3.6 High         | AI Vision (equipment detection), OCR (invoices/blueprints), complex data reasoning |

---

## 📦 Module → Agent Assignment

| #   | Module / Workstream                                          | Bounded Context                          | Owner                 | Support | Phase   |
| --- | ------------------------------------------------------------ | ---------------------------------------- | --------------------- | ------- | ------- |
| M0  | **Platform Architecture & Monorepo**                         | `/`, `packages/`, `infra/`               | **Agent 1**           | Agent 4 | 1       |
| M1  | **Auth, RBAC, Multi-Tenancy**                                | `services/auth-service`                  | **Agent 1**           | —       | 1       |
| M2  | **API Gateway / BFF**                                        | `apps/api-gateway`                       | **Agent 1**           | Agent 2 | 1       |
| M3  | **Database Architecture & Migrations**                       | `packages/types`, per-service DB         | **Agent 1**           | Agent 2 | 1       |
| M4  | **Customer CRM**                                             | `services/customer-service`              | **Agent 2**           | —       | 1       |
| M5  | **Lead Management**                                          | `services/customer-service`              | **Agent 2**           | —       | 2       |
| M6  | **Pricebook** (materials/labor/regional)                     | `services/pricebook-service`             | **Agent 2**           | —       | 1       |
| M7  | **Quote / Estimate Engine**                                  | `services/quote-service`                 | **Agent 2**           | Agent 1 | 1       |
| M8  | **Proposal Builder**                                         | `services/proposal-service`              | **Agent 2**           | Agent 4 | 2       |
| M9  | **PDF Engine**                                               | `services/proposal-service`              | **Agent 4**           | Agent 2 | 1       |
| M10 | **E-Signature + Audit Trail**                                | `services/proposal-service`              | **Agent 4**           | Agent 1 | 2       |
| M11 | **Payments** (Stripe/Square/ACH)                             | `services/payment-service`               | **Agent 4**           | Agent 1 | 3       |
| M12 | **Web Frontend + Design System**                             | `apps/web`, `packages/ui`                | **Agent 2**           | Agent 3 | 1       |
| M13 | **Mobile App (Flutter)**                                     | `apps/mobile`                            | **Agent 4**           | Agent 2 | 3       |
| M14 | **Offline Sync Engine**                                      | `apps/mobile`, `services/quote-service`  | **Agent 4**           | Agent 1 | 3       |
| M15 | **AI Quote Assistant** (voice→quote, scope/proposal writing) | `services/ai-service`                    | **Agent 1**           | Agent 3 | 2       |
| M16 | **AI Copilot** ("how much / what's missing / rewrite")       | `services/ai-service`                    | **Agent 1**           | —       | 2       |
| M17 | **AI Sales Coach** (upsell/warranty/cross-sell)              | `services/ai-service`                    | **Agent 3 (High)**    | Agent 1 | 3       |
| M18 | **AI Vision** (panel/HVAC/pipe/roof detection)               | `services/ai-service`                    | **Agent 3 (High)**    | Agent 1 | 3       |
| M19 | **AI OCR** (invoices/blueprints/handwriting)                 | `services/ai-service`                    | **Agent 3 (High)**    | Agent 1 | 3       |
| M20 | **Dashboard**                                                | `apps/web`, `services/analytics-service` | **Agent 2**           | Agent 3 | 2       |
| M21 | **Analytics** (KPIs, forecasts, LTV)                         | `services/analytics-service`             | **Agent 3 (Med)**     | Agent 2 | 3       |
| M22 | **Notifications** (Email/SMS/WhatsApp/Push)                  | `services/notification-service`          | **Agent 4**           | Agent 3 | 2       |
| M23 | **Integrations** (QuickBooks/Xero/Zapier/FSM)                | `services/integration-service`           | **Agent 3 (Med)**     | Agent 4 | 3       |
| M24 | **DevOps / CI-CD / IaC**                                     | `infra/`, `.github/workflows`            | **Agent 4**           | Agent 1 | 1       |
| M25 | **Testing & QA Strategy**                                    | all + `ai/eval`                          | **Agent 3 (Low/Med)** | all     | ongoing |
| M26 | **Documentation & Technical Writing**                        | `docs/`                                  | **Agent 3 (Low)**     | Agent 1 | ongoing |
| M27 | **Security Hardening & OWASP**                               | cross-cutting                            | **Agent 1**           | Agent 4 | ongoing |

---

## 🔄 Coordination Rules

1. **Contracts before code.** Agent 1 publishes the OpenAPI/gRPC + domain-event schema for a service in `docs/` before implementation agents build against it.
2. **One writer per file.** Never two agents editing the same file concurrently. Coordinate through `TASKS.md` status.
3. **Shared types live in `packages/types`** — Agent 1 owns breaking changes.
4. **Every PR must pass the 12 Quality Gates** (see CTO Directive) before Agent 1 sign-off.
5. **Blocked?** Set the task to `BLOCKED` in `TASKS.md` + note the dependency; Agent 1 unblocks.
6. **Definition of Done** = code + tests (≥80% on domain logic) + docs updated + tracker row `DONE` + gate checklist green.
