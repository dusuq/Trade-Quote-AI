# 🚀 T201 — AI Quote Assistant: CTO Implementation Prompt

> **How to use:** Paste this entire document into a **new Claude Code (Opus 4.8) session** as Agent 1 (CTO).
> It is self-contained — read it fully, then begin implementation.

---

## Your Identity & Context

You are **Agent 1 (CTO)** for TradeQuote AI — the chief architect and owner of the AI service.
You are about to implement **T201: AI Quote Assistant (voice→text→structured scope→line items)**.

- **Task ID:** `T201`
- **Module:** M15
- **Your lane:** Agent 1 (Opus 4.8)
- **Support:** Agent 3 (Gemini / Antigravity)
- **Dependency:** T106 ✅ (Quote Engine — done & CTO-audited)
- **Unblocks:** T202 (AI Copilot), T304/T305/T306 (Vision/OCR/Sales Coach)

---

## Step 1 — Read the Plan

A complete, architecture-level implementation plan has been prepared by Agent 3 and is waiting at:

```
docs/modules/M15-ai-quote-assistant-plan.md
```

**Read it now.** It contains:
- Full architecture + sequence diagrams (voice-to-quote, text-to-quote)
- Clean Architecture file inventory (42 files across service, DB migration, gateway, tests)
- API contract (4 endpoints: `/voice-to-quote`, `/text-to-quote`, `/scope-writer`, `/usage`)
- Domain models, protocols, use cases, infrastructure adapters
- Database migration `0009_ai_service.sql` with RLS
- Gateway wiring (port 8008, config + server changes)
- LLM prompts (scope extraction, scope writer)
- Test suite design (10 test files, ≥80% coverage, all external APIs stubbed)
- Quality Gates checklist

---

## Step 2 — Read the Conventions

Before writing any code, re-read the mandatory conventions:

```
docs/07-SERVICE-CONVENTIONS.md
```

Key rules that apply to `ai-service`:
1. **No JWT decode** — trust `x-tenant-id`/`x-user-id` headers from the gateway
2. **Clean Architecture** — `domain/` → `application/` → `infrastructure/` → `interface/`
3. **Money** — integer minor units (`*_minor: int`, cents) + ISO-4217. Never floats.
4. **Rates** — basis points (`*_bps: int`; 10000 = 100%)
5. **Time** — `datetime.now(UTC)` (not `timezone.utc`)
6. **Tooling** — `pyproject.toml` must declare `[tool.ruff]`, `[tool.mypy]`, bugbear exemptions
7. **Gateway** — add service to `apps/api-gateway/src/config.ts` + `server.ts`
8. **Events** — use canonical names from `packages/types/src/events.ts`

Reference implementations: `services/customer-service` (Repository Pattern) and `services/pricebook-service`.

---

## Step 3 — Resolve Open Questions

The plan has 3 open questions. As CTO, decide before coding:

### Q1: Pricebook Matching — HTTP vs Shared DB?
- **Recommendation:** HTTP call to `pricebook-service` (preserves bounded-context isolation)
- **Note:** This introduces a sync service-to-service call. T307b audit flagged this pattern.
- **Decision needed:** Write ADR-0003 for sync service-to-service HTTP calls? Or defer?

### Q2: Scope Writer — Include in T201 or defer to T202?
- **Recommendation:** Include basic `POST /v1/ai/scope-writer` in T201 (shares LLM infra)
- T202 adds the full copilot (pricing analysis, missing items, rewrite)

### Q3: Web UI — Backend-only or include UI?
- **Recommendation:** Backend API only in T201; web UI as T201b follow-up (mirrors T204/T204b)

---

## Step 4 — Implement

### Implementation Order

1. **Project scaffold** — `pyproject.toml`, `main.py`, `app/config.py`, directory structure
2. **Domain layer** — `models.py`, `events.py`, `errors.py`, `protocols.py` (pure, no I/O)
3. **Infrastructure** — `db.py`, `whisper_adapter.py`, `claude_adapter.py`, `pricebook_client.py`, `quote_client.py`, `usage_repository.py`
4. **Application** — `voice_to_quote.py`, `text_to_quote.py`, `scope_writer.py` (use cases)
5. **Interface** — `routes.py`, `schemas.py` (thin HTTP adapter)
6. **Database migration** — `infra/db/migrations/0009_ai_service.sql`
7. **Gateway wiring** — `config.ts` + `server.ts` changes
8. **Tests** — all 10 test files, ≥80% domain/application coverage
9. **Verification** — `ruff check`, `mypy app`, `pytest`, `check_conventions.py`, gateway tests

### Port Assignment
- **ai-service: port 8008** (after esign-service on 8007)

### Key Dependencies (Python)
```
fastapi, uvicorn, pydantic, httpx, anthropic, openai, python-multipart,
sqlalchemy, psycopg2-binary
```
Dev: `pytest, ruff, mypy`

---

## Step 5 — Update Tracker

When done:
1. Check the box in `TASKS.md`: `- [x] T201 ...`
2. Update `tracking/PROGRESS-TRACKER.csv`: status → `DONE`, fill end date
3. Scan T201's dependents and unblock T202 in the "Ready now" table

---

## Step 6 — Definition of Done

- [ ] `services/ai-service/` fully implemented (Clean Architecture)
- [ ] 4 API endpoints working (`/voice-to-quote`, `/text-to-quote`, `/scope-writer`, `/usage`)
- [ ] `infra/db/migrations/0009_ai_service.sql` created with RLS
- [ ] Gateway wired (`/v1/ai` → `http://localhost:8008`)
- [ ] `ruff check app tests` — clean
- [ ] `mypy app` — clean
- [ ] `pytest tests/` — all pass, ≥80% on domain/application
- [ ] `python scripts/check_conventions.py` — green
- [ ] Gateway tests (`pnpm test`) — green
- [ ] Domain events match `packages/types`: `ai.quote.drafted`, `ai.usage.recorded`
- [ ] Money is integer minor units, rates are basis points — verified in tests
- [ ] No `import jwt` anywhere in `ai-service`
- [ ] Doc: `docs/modules/M15-ai-quote-assistant.md` spec written

---

## Quick Reference: Existing Services (for patterns)

| Service            | Port | Route Prefix         | Style              |
|--------------------|------|----------------------|---------------------|
| auth-service       | 8001 | `/v1/auth`           | Session-injection   |
| customer-service   | 8002 | `/v1/customers`      | Repository Protocol |
| pricebook-service  | 8003 | `/v1/pricebook`      | Repository Protocol |
| quote-service      | 8004 | `/v1/quotes`         | Session-injection   |
| proposal-service   | 8005 | `/v1/proposals`      | Repository Protocol |
| analytics-service  | 8006 | `/v1/analytics`      | Repository Protocol |
| esign-service      | 8007 | `/v1/signature-*`    | Repository Protocol |
| **ai-service**     | **8008** | **`/v1/ai`**     | **Repository Protocol** |

---

**Begin now. Read `docs/modules/M15-ai-quote-assistant-plan.md` first, then start coding.**
