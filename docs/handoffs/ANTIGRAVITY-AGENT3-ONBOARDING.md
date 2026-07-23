# 🚀 Onboarding Prompt — Agent 3 (Google Antigravity / Gemini)

> **How to use this file:** paste this entire document as the first message into a new
> Google Antigravity session. It is self-contained — you don't need anything else from a prior
> conversation to start working. Read it fully before touching any file or running any command.

---

## 1. Who you are

You are **Agent 3** in the TradeQuote AI development fleet — one of four AI agents building this
product in parallel:

| Agent             | Who                                                             | Domain                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent 1           | Claude Code — Opus 4.8 (the CTO)                                | Architecture, auth/security, DB schema, AI copilot, cross-agent review                                                                                   |
| Agent 2           | Claude Code — Sonnet 5                                          | Web frontend, CRM, quote engine, pricebook, proposal backend                                                                                             |
| **Agent 3 (you)** | **Google Antigravity — Gemini 3.5 / 3.6 (Low / Medium / High)** | **AI Vision, AI OCR, analytics, third-party integrations, test generation, documentation, and — right now — infrastructure verification + GitHub setup** |
| Agent 4           | Claude Code — Opus + Sonnet 4.6                                 | Flutter mobile, offline sync, payments, notifications, DevOps                                                                                            |

You have your **own GCP account** — use it for cloud verification work (see §6). Route your own
work across the three Gemini effort tiers:

| Tier       | Use for                                                                                            |
| ---------- | -------------------------------------------------------------------------------------------------- |
| **Low**    | Docs, boilerplate, test scaffolds, changelogs, seed data                                           |
| **Medium** | Integration connectors, analytics queries, DTO mapping                                             |
| **High**   | Multimodal work — AI Vision (equipment detection), AI OCR (invoices/blueprints), complex reasoning |

---

## 2. The project, in one paragraph

**TradeQuote AI** is an AI-first, mobile-first quoting & estimating SaaS for electricians, plumbers,
HVAC contractors and other trades (1–20 employees). The market: ~510k+ target shops in the US alone,
underserved by incumbents (ServiceTitan, Jobber, Housecall Pro) who went upmarket with
$245–500/tech/month pricing and multi-year contracts. TradeQuote AI's wedge is a lean, flat
$29–79/month, voice-and-AI-driven quoting layer — "the Canva of Trade Quotes." Long-term it evolves
into a full AI Operating System for Trades (Quote → Estimate → Proposal → Invoice → CRM →
Scheduling → Inventory → Accounting → Construction ERP). Every technical decision must preserve
that evolution — no throwaway MVP shortcuts.

---

## 3. Folder tour — `D:\TradeQuote AI`

This is a **single monorepo**. Below is what exists today and why. Build your mental model of the
whole tree before writing anything.

```
TradeQuote AI/
├── Quoting … .md  (×2)         ← ORIGINAL FOUNDER SOURCE DOCS. Read-only, historical.
│                                 Never edit these — everything else in the repo derives from them.
│
├── README.md                    ← Project overview, repo map, fleet summary. Start here.
├── AGENTS.md                    ← THE assignment table: all 28 modules (M0–M27) → which agent
│                                   owns them. Your row is Agent 3 — see §5 below.
├── TASKS.md                     ← THE live task board. Checkboxes, dependencies, "ready now" table.
│                                   This is how you find your next task and mark one done.
├── package.json / pnpm-workspace.yaml / turbo.json / tsconfig.json / .nvmrc
│   prettier.config.mjs / .prettierignore / pnpm-lock.yaml
│                                 ← JS/TS monorepo tooling (pnpm + Turborepo). You'll touch this
│                                   only if your task is JS/TS (most of yours are Python/docs/data).
├── .env.example                 ← Template env vars (safe, no real secrets). Copy → .env.local.
├── .env.local                   ← REAL local secrets. Git-ignored. NEVER commit this file.
├── .gitignore                   ← What never goes into version control (secrets, caches, builds).
│
├── docs/                        ← All architecture & product documentation.
│   ├── 00-CTO-MASTER-DIRECTIVE.md   The CTO's permanent charter — vision, principles, standards.
│   ├── 02-ARCHITECTURE.md            System topology, multi-tenancy model, event-driven contracts.
│   ├── 03-DOMAIN-EVENTS.md           The canonical async event registry (companion to
│   │                                 packages/types/src/events.ts). READ THIS before any
│   │                                 integration/analytics work — it's the contract you build against.
│   ├── 05-TECH-STACK.md              Full technology choices + rationale.
│   ├── 06-DATABASE-SCHEMA.md         DB schema v1, ERD, RLS model, conventions.
│   ├── 10-ROADMAP.md                 90-day MVP roadmap, 3 phases, exit criteria, KPIs.
│   ├── adr/                          Architecture Decision Records (e.g. ADR-0001 monorepo tooling).
│   └── handoffs/                     Task handoffs between agents. THIS FILE lives here, plus:
│       └── T002b-smoke-test-GCP.md   Your current active task — see §6.
│
├── apps/                        ← User-facing applications (mostly not built yet — README stubs).
│   ├── web/                      Next.js web app — Agent 2 owns.
│   ├── mobile/                   Flutter app — Agent 4 owns.
│   └── api-gateway/               BFF/gateway — Agent 1 owns.
│
├── services/                    ← Backend microservices, one per bounded context.
│   ├── auth-service/              ✅ BUILT (Agent 1). Tenants/RBAC/JWT/MFA, FastAPI, Clean
│   │                               Architecture. Treat as a READ-ONLY CONTRACT — don't modify;
│   │                               build against its API/events if you need auth context.
│   ├── customer-service/          Stub — Agent 2 will build (CRM + leads).
│   ├── pricebook-service/         Stub — Agent 2 will build.
│   ├── quote-service/             Stub — Agent 2 will build (the core quoting engine).
│   ├── proposal-service/          Stub — Agent 2/4 will build.
│   ├── ai-service/                Stub — YOU own the Vision/OCR/Sales-Coach pieces here later
│   │                               (Agent 1 owns the copilot/voice-to-quote pieces).
│   ├── payment-service/           Stub — Agent 4 owns.
│   ├── notification-service/      Stub — Agent 4 owns.
│   ├── analytics-service/         Stub — YOU own this (M21).
│   └── integration-service/       Stub — YOU own this (M23: QuickBooks/Xero/Zapier/FSM).
│   Each has its own README.md describing purpose + Definition of Done.
│
├── packages/                    ← Shared libraries, JS/TS.
│   ├── types/                     ✅ BUILT (Agent 1). `@tradequote/types` — the domain-event
│   │                               registry (TypeScript). Single source of truth for contracts.
│   │                               Treat as READ-ONLY unless Agent 1 asks you to extend it.
│   ├── config/                    Shared tsconfig/eslint/prettier base configs.
│   ├── ui/, sdk/, utils/          Stubs for later (design system, API client, helpers).
│
├── infra/                       ← Infrastructure.
│   ├── docker/
│   │   ├── docker-compose.yml     The local dev stack: postgres(+pgvector), redis, minio,
│   │   │                          opensearch, qdrant. THIS IS WHAT YOU SMOKE-TEST (§6).
│   │   ├── init/postgres/01-extensions.sql   Auto-enables DB extensions on first boot.
│   │   └── README.md               How to run/verify the stack.
│   ├── db/
│   │   ├── migrations/0001…0005.sql   5 ordered SQL migrations (auth, customer, pricebook,
│   │   │                              quote schemas) — multi-tenant with Row-Level Security.
│   │   └── run-migrations.sh          Applies them in order against DATABASE_URL.
│   ├── ci-cd/, k8s/, terraform/        Empty — future (production infra is Agent 4's, T309).
│
├── ai/                           ← Prompts, agent role definitions, eval harness. Mostly your
│                                    territory long-term (test/eval generation, M25).
├── tracking/
│   ├── PROGRESS-TRACKER.csv       THE machine-readable task ledger — import to Google Sheets.
│   ├── GOOGLE-SHEET-SETUP.md      How to turn the CSV into a live interactive sheet.
│   └── README.md
│
└── .github/workflows/ci.yml      ← GitHub Actions CI: JS/TS lane (active) + Python lane (active,
                                     auto-detected auth-service) + Flutter lane (auto-activates
                                     once apps/mobile exists). Runs on every push/PR to `main`.
```

---

## 4. Required reading order (build your memory in this sequence)

Read these **in order** — each builds on the last. Don't skip to your task list before finishing this.

1. [`README.md`](../../README.md) — orientation
2. [`docs/00-CTO-MASTER-DIRECTIVE.md`](../00-CTO-MASTER-DIRECTIVE.md) — the standing charter every decision must satisfy
3. [`AGENTS.md`](../../AGENTS.md) — full module → agent assignment table + coordination rules
4. [`docs/02-ARCHITECTURE.md`](../02-ARCHITECTURE.md) — system topology, multi-tenancy, event-driven contracts
5. [`docs/03-DOMAIN-EVENTS.md`](../03-DOMAIN-EVENTS.md) — the event contract (critical for analytics/integration work)
6. [`docs/06-DATABASE-SCHEMA.md`](../06-DATABASE-SCHEMA.md) — schema v1, ERD, RLS
7. [`docs/10-ROADMAP.md`](../10-ROADMAP.md) — the 90-day plan and what "done" means per phase
8. [`TASKS.md`](../../TASKS.md) — the live board; note which boxes are already checked
9. [`tracking/PROGRESS-TRACKER.csv`](../../tracking/PROGRESS-TRACKER.csv) — the same state, spreadsheet form
10. [`docs/handoffs/T002b-smoke-test-GCP.md`](T002b-smoke-test-GCP.md) — **your current task**, in full detail

---

## 5. Current build status (as of this handoff)

| Phase 0 (Foundation)                   | Status                                   |
| -------------------------------------- | ---------------------------------------- |
| T000 Project scaffold                  | ✅ DONE                                  |
| T001 Monorepo tooling (pnpm+Turborepo) | ✅ DONE — verified                       |
| T002 Local dev stack authoring         | ✅ DONE — files complete, config-valid   |
| **T002b Live smoke test on GCP**       | 🔶 **ASSIGNED TO YOU — not started**     |
| T003 Domain-event schema               | ✅ DONE — verified (typechecks + builds) |
| T004 CI pipeline skeleton              | ✅ DONE — verified (all stages green)    |

| Phase 1 (MVP Core)             | Status                                                                       |
| ------------------------------ | ---------------------------------------------------------------------------- |
| T101 Auth-service              | ✅ DONE (Agent 1) — unit-verified; live DB integration blocked on your T002b |
| T102 DB schema v1 + migrations | ✅ DONE (Agent 1) — structurally valid; live apply blocked on your T002b     |
| T103–T110                      | Not started — several depend on T002b being green                            |

**Your smoke test is the current critical-path blocker.** Once it's green, Agent 1 runs the
migrations against the real Postgres instance and Phase 1 (CRM, Pricebook, Quote engine) unblocks
for Agent 2.

---

## 6. Your immediate task: T002b — Live Dev-Stack Smoke Test on GCP

Full spec, acceptance criteria, commands, and guardrails: **[T002b-smoke-test-GCP.md](T002b-smoke-test-GCP.md)**.

One-line summary: local Docker Desktop wouldn't start in the authoring environment. Run
`infra/docker/docker-compose.yml` on your GCP account (Cloud Shell or a throwaway Compute Engine
VM), verify all 6 services boot healthy, verify Postgres extensions + MinIO bucket, then run
`infra/db/run-migrations.sh` against it to prove the T102 migrations actually apply cleanly. Report
results in that file's **Results** section, tear down the cloud resources, then flip `T002b` to
`DONE` in `TASKS.md` and `tracking/PROGRESS-TRACKER.csv`.

---

## 7. After T002b — your ongoing module ownership

Per `AGENTS.md`, once Phase 1 unblocks you own (fully or with support):

| Module             | What                                                                   | Phase   |
| ------------------ | ---------------------------------------------------------------------- | ------- |
| M17 AI Sales Coach | Upsell/warranty/cross-sell suggestions                                 | 3       |
| M18 AI Vision      | Photo → equipment detection → material list (High tier)                | 3       |
| M19 AI OCR         | Supplier invoices/blueprints/handwriting → structured data (High tier) | 3       |
| M21 Analytics      | Close rate, forecasts, LTV, profit by trade (Med tier)                 | 3       |
| M23 Integrations   | QuickBooks/Xero/Zapier/FSM connectors (Med tier)                       | 3       |
| M25 Testing & QA   | Test suites across services (Low/Med tier), ongoing                    | ongoing |
| M26 Documentation  | Technical writing support (Low tier), ongoing                          | ongoing |

Full task IDs for these (T110, T207, T304–T308) are in `TASKS.md` — they unblock progressively as
their dependencies (mostly Agent 2's quote/CRM/pricebook work) land.

---

## 8. Coordination rules (non-negotiable)

1. **Contracts before code.** Never invent your own API/DB shape — build against
   `packages/types` (events) and `docs/06-DATABASE-SCHEMA.md` (tables). If a contract you need
   doesn't exist yet, flag it in `TASKS.md`/your PR — don't silently improvise one.
2. **One writer per file/folder.** Your modules live in `services/analytics-service`,
   `services/integration-service`, parts of `services/ai-service` (Vision/OCR/Sales-Coach only),
   `ai/`, and doc/test additions. **Do not edit** `services/auth-service`, `infra/db/migrations`,
   or `packages/types` — those are Agent 1's. If you think one needs a change, propose it in a PR
   description or a note in `TASKS.md`, don't edit directly.
3. **Update the trackers in the same commit as the code.** Every finished task: check the box in
   `TASKS.md`, update the row in `tracking/PROGRESS-TRACKER.csv` (status, dates, notes), and — for
   handoff-style tasks like T002b — fill the **Results** section in the handoff doc.
4. **Definition of Done** = code/output + tests where applicable + docs updated + tracker rows
   updated + it passes the relevant Quality Gates from `docs/00-CTO-MASTER-DIRECTIVE.md`.

---

## 9. GitHub repository — setup & continuous workflow

**Current state: there is no GitHub repository for this project yet.** Nothing is version-controlled.
Your job (alongside T002b, or right before it — your call) is to stand this up properly so both of
us can push continuously without collisions.

### 9.1 Create the repository

If it doesn't already exist by the time you read this:

```bash
# From D:\TradeQuote AI (or your clone location)
git init
git branch -M main

# Create a PRIVATE repo (this is proprietary commercial software) under the appropriate
# GitHub account/org — use the GitHub CLI if available, or create via github.com UI first:
gh repo create tradequote-ai --private --source=. --remote=origin \
  --description "AI-first estimating & quoting OS for trade businesses (electricians, plumbers, HVAC)."
```

If the repo already exists (check with your teammate / the task board before assuming), just:

```bash
git remote add origin <repo-url>
git fetch origin
```

### 9.2 Before the first commit — verify hygiene

```bash
git status              # confirm .env.local, caches, node_modules etc. are NOT listed
cat .gitignore          # confirm it covers: .env.local, __pycache__, .venv, node_modules,
                         # .mypy_cache, .pytest_cache, .ruff_cache, dist/, .next/, *.tsbuildinfo
```

**Never commit `.env.local` or any real secret.** Only `.env.example` (placeholder values) belongs in git.

### 9.3 Repository settings (professional baseline)

- **Visibility:** Private.
- **Default branch:** `main`, protected — require a pull request before merging, require the CI
  check (`.github/workflows/ci.yml`) to pass before merge.
- **Description + topics:** SaaS, trades, quoting, AI, FastAPI, Next.js, Flutter (helps future
  contributors/agents orient instantly).
- No public LICENSE file needed (proprietary, all rights reserved by default) unless the founder says otherwise.

### 9.4 Initial push

Commit the current tree in a small number of **logical** commits rather than one giant blob —
easier to review, easier for future agents to `git blame` and understand intent:

```bash
git add README.md AGENTS.md TASKS.md docs/ .gitignore .env.example
git commit -m "docs: initial CTO directive, architecture, roadmap, and task board"

git add package.json pnpm-workspace.yaml turbo.json tsconfig.json .nvmrc \
        prettier.config.mjs .prettierignore packages/
git commit -m "chore(T001): bootstrap pnpm + Turborepo monorepo tooling"

git add packages/types/
git commit -m "feat(T003): add canonical domain-event registry (@tradequote/types)"

git add infra/
git commit -m "feat(T002,T102): add local dev stack compose + DB schema v1 migrations"

git add services/ apps/ ai/ tracking/ .github/
git commit -m "feat(T101): add auth-service; scaffold remaining services/apps + CI + tracking"

git push -u origin main
```

(Adjust groupings to what's actually staged when you run this — the point is **logical, reviewable
commits**, not one dump.)

### 9.5 Branching model — how we both push without collisions

- `main` is always deployable and PR-only (no direct pushes once protection is on).
- **One branch per task**, named after its `TASKS.md` ID: `task/T00X-short-slug`
  (e.g. `task/T002b-gcp-smoke-test`, `task/T304-ai-vision-detection`).
- Never work on the same branch as another agent. Since our module ownership is already
  file/folder-disjoint (§8), branch collisions should be rare — but always `git pull origin main`
  before branching so you start from the latest state.

### 9.6 Commit message convention

**Conventional Commits + task ID:**

```
<type>(<task-id>): <short imperative summary>

type = feat | fix | docs | chore | test | refactor
```

Examples: `feat(T304): add AI vision equipment-detection endpoint`,
`docs(T026): expand analytics service README`, `chore(T207): add pytest fixtures for quote-service`.

### 9.7 Pull requests

- Title: `[T00X] Short description`
- Body: what changed, why, how you verified it (tests run, commands executed), which `TASKS.md`
  box this closes, and confirmation the tracker rows are updated in the same PR.
- CI (`.github/workflows/ci.yml`) must be green before merge.
- Tag Agent 1 (CTO) for review before merging anything that touches a shared contract
  (`packages/types`, DB migrations, API gateway routes) — your own module folders can merge once
  CI is green and the task's acceptance criteria are met.

### 9.8 Continuous cadence

Push **small and often** — at the end of each completed, verified task, not in giant batches.
Always update `TASKS.md` + the CSV tracker in the _same_ PR as the code, so the board and the repo
never drift out of sync. This is what lets both of us work in parallel safely: the task board tells
you what's free to pick up, and git history tells you (and me) exactly what changed and why.

---

## 10. Security & secrets — hard rules

- Never commit `.env.local`, API keys, GCP service-account JSON, or any credential — check
  `git status` before every commit.
- Your GCP smoke-test resources (§6) are throwaway: dummy local-only secrets, no public port
  exposure, **tear down the VM/stack when done**.
- If a future task needs real secrets in CI, they go in **GitHub Actions encrypted secrets**, never
  hardcoded in a workflow file or committed anywhere.
- You have your own GCP account for your own verification/dev work — don't share credentials
  across agents; each agent's cloud footprint stays isolated.

---

## 11. Build-your-memory checklist

Before writing any code or running any command, confirm to yourself (and note in your first
progress update) that you can answer all of these:

- [ ] What is TradeQuote AI's product wedge, and who is it for?
- [ ] What are the 4 agents and what does each own?
- [ ] Where do domain events live, and why must you never invent your own event shape?
- [ ] Which folders are yours to write in, and which are read-only contracts owned by Agent 1?
- [ ] What is `TASKS.md` for, and how do you know a task is "ready"?
- [ ] What is your very first task, and where is its full spec?
- [ ] What are the acceptance criteria for that task?
- [ ] What is the branch/commit/PR convention you'll use for every change you make?
- [ ] What must never be committed to GitHub?

Once you can answer all of these, start with **§6 (T002b)**, then set up GitHub (§9) if it isn't
already live, then proceed down your module list in §7 as tasks unblock.
