# 🚀 TradeQuote AI

> **"The Canva of Trade Quotes."** — The AI-First Estimating Operating System for Trade Businesses.

AI-powered, mobile-first quoting & estimating platform for electricians, plumbers, HVAC contractors, and other trades. Create professional estimates in **minutes instead of hours**.

|                    |                                             |
| ------------------ | ------------------------------------------- |
| **Version**        | 1.0 (MVP in progress)                       |
| **Product Type**   | Vertical SaaS (B2B)                         |
| **Target Market**  | Small trade businesses (1–20 employees)     |
| **Business Model** | Subscription SaaS + AI Usage + Marketplace  |
| **Markets**        | USA · Canada · UK · Australia · New Zealand |

---

## 📁 Repository Layout

```
TradeQuote AI/
├── apps/                # User-facing applications
│   ├── web/             # Next.js web app (Owner Agent: Agent 2 — Sonnet 5)
│   ├── mobile/          # Flutter iOS/Android/Tablet (Owner: Agent 4)
│   └── api-gateway/     # API gateway / BFF (Owner: Agent 1)
├── services/            # Backend microservices (bounded contexts)
│   ├── auth-service/            # Auth, RBAC, tenants   (Agent 1)
│   ├── customer-service/        # CRM + Leads           (Agent 2)
│   ├── quote-service/           # Quote/estimate engine (Agent 2)
│   ├── pricebook-service/       # Material/labor library(Agent 2)
│   ├── proposal-service/        # Proposal + PDF + Sign (Agent 2/4)
│   ├── ai-service/              # AI copilot/voice/NLP  (Agent 1)
│   ├── payment-service/         # Stripe/Square/ACH     (Agent 4)
│   ├── notification-service/    # Email/SMS/WhatsApp/Push(Agent 4)
│   ├── analytics-service/       # KPIs, dashboards      (Agent 3)
│   └── integration-service/     # QuickBooks/Zapier/etc (Agent 3)
├── packages/            # Shared libraries (ui, types, sdk, config, utils)
├── ai/                  # Prompts, agent definitions, eval harness
├── infra/               # Docker, K8s, Terraform, CI/CD
├── docs/                # PRDs, architecture, ADRs, module specs
├── tracking/            # Progress CSV (Google-Sheet import) + dashboards
├── .github/workflows/   # GitHub Actions pipelines
├── TASKS.md             # ✅ Master task board — mark done + find next task
├── AGENTS.md            # 🤖 The 4 dev agents + module assignments
└── docs/00-CTO-MASTER-DIRECTIVE.md  # The permanent CTO system prompt
```

---

## 🤖 The Development Fleet

Four AI development agents build this platform in parallel. See **[AGENTS.md](AGENTS.md)** for full capability matrix and module assignments.

> **Onboarding a new agent session?** Google Antigravity (Agent 3) has a self-contained cold-start
> prompt at [docs/handoffs/ANTIGRAVITY-AGENT3-ONBOARDING.md](docs/handoffs/ANTIGRAVITY-AGENT3-ONBOARDING.md)
> — folder tour, reading order, current task queue, and the GitHub repo/branching workflow.

| #   | Agent                                         | Model(s)                        | Primary Domain                                                    |
| --- | --------------------------------------------- | ------------------------------- | ----------------------------------------------------------------- |
| 1   | **Claude Code — Opus 4.8** (this agent / CTO) | `claude-opus-4-8`               | Architecture, AI service, auth/security, DB design, orchestration |
| 2   | **Claude Code — Sonnet 5**                    | `claude-sonnet-5`               | Web frontend, CRM, quote/pricebook/proposal backends              |
| 3   | **Google Antigravity — Gemini**               | Gemini 3.5 / 3.6 (Low·Med·High) | Vision, OCR, analytics, integrations, tests, docs                 |
| 4   | **Claude Code — Opus + Sonnet 4.6**           | `claude-opus` / `sonnet-4.6`    | Flutter mobile, offline sync, payments, notifications, DevOps     |

---

## 🏁 Getting Started (for any agent picking up work)

1. Read **[docs/00-CTO-MASTER-DIRECTIVE.md](docs/00-CTO-MASTER-DIRECTIVE.md)** — the standing engineering charter.
2. Read **[AGENTS.md](AGENTS.md)** — find the modules assigned to you.
3. Open **[TASKS.md](TASKS.md)** — pick the next `TODO` task in your lane whose dependencies are `DONE`.
4. Update **[tracking/PROGRESS-TRACKER.csv](tracking/PROGRESS-TRACKER.csv)** (or the linked Google Sheet): set status to `IN_PROGRESS`, add start date.
5. Build to spec (see the module's folder README + `docs/modules/`). Pass all Quality Gates.
6. On completion: check the box in `TASKS.md`, set CSV row to `DONE`, log the next dependent task.

---

## 🔐 Environment

Copy `.env.example` → `.env.local` and fill in secrets. **Never commit `.env.local`.** See [.env.example](.env.example) for the full variable list.

---

## 🧱 Tech Stack (summary)

**Frontend:** Next.js · React · TypeScript · Tailwind · shadcn/ui · TanStack Query · Zustand
**Mobile:** Flutter (offline-first, SQLite/Drift, WatermelonDB-style sync)
**Backend:** FastAPI (Python) · Node.js (realtime/WebSockets) · REST + gRPC
**AI:** Anthropic Claude · OpenAI · Whisper/STT · Vision · pgvector/Qdrant
**Data:** PostgreSQL (multi-tenant) · Redis · S3-compatible object storage · OpenSearch
**Auth:** Clerk/Auth0 · OAuth · MFA · RBAC
**Infra:** Docker · Kubernetes-ready · GitHub Actions · Cloudflare · Vercel · Railway/Fly.io (MVP)
**Observability:** OpenTelemetry · Prometheus · Grafana · Loki · Sentry

Full detail: [docs/05-TECH-STACK.md](docs/05-TECH-STACK.md)
