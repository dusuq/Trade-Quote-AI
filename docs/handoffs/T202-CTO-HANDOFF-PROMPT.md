# 🚀 T202 — AI Copilot: CTO Implementation Prompt

> **How to use:** Paste this entire document into a **new Claude Code (Opus 4.8) session** as Agent 1 (CTO).
> It is self-contained — read it fully, then begin implementation.

---

## Your Identity & Context

You are **Agent 1 (CTO Core)** for TradeQuote AI — the chief architect and owner of the AI service.
You are about to implement **T202: AI Copilot (pricing analysis, margin check, missing items detection, and text rewriting)**.

- **Task ID:** `T202`
- **Module:** M16
- **Your lane:** Agent 1 (Opus 4.8)
- **Support:** Agent 3 (Gemini / Antigravity)
- **Dependency:** T106 ✅ (Quote Engine — done & CTO-audited), T201 ✅ (AI Quote Assistant — done & CTO-audited)
- **Unblocks:** T304 (AI Vision), T305 (AI OCR), T306 (AI Sales Coach)

---

## Step 1 — Read the Plan

A complete, architecture-level implementation plan has been prepared by Agent 3 and is waiting at:

```
docs/modules/M16-ai-copilot-plan.md
```

**Read it now.** It contains:
- Full architecture + sequence diagrams (pricing analysis, missing items, rewrite)
- File inventory (23 changes: 8 new app/infra files, 6 modified files, 8 new test files, 1 doc)
- API contract (3 endpoints: `/v1/ai/copilot/analyze-pricing`, `/v1/ai/copilot/missing-items`, `/v1/ai/copilot/rewrite`)
- Domain models, protocols, use cases, infrastructure adapters
- Prompt engineering templates and JSON structured schemas (`output_config.format` JSON schemas)
- Test suite design (8 test files, ≥80% coverage, all external APIs stubbed)
- Quality Gates checklist

---

## Step 2 — Read the Conventions

Ensure your implementation complies with:

```
docs/07-SERVICE-CONVENTIONS.md
```

Key rules that apply to `ai-service`:
1. **No JWT decode** — trust `x-tenant-id`/`x-user-id` headers from the gateway.
2. **Clean Architecture** — `domain/` → `application/` → `infrastructure/` → `interface/`
3. **Money** — integer minor units (`*_minor: int`, cents) + ISO-4217. Never floats.
4. **Rates** — basis points (`*_bps: int`; 10000 = 100%).
5. **Time** — `datetime.now(UTC)` (not `timezone.utc`).
6. **Tooling** — keep ruff/mypy clean and verify with conventions check.
7. **No Side Effects** — All copilot endpoints are read-only and return advice. They do not write to quotes.

---

## Step 3 — Resolve Open Questions

The plan recommends the following decisions. Confirm these or adjust them if needed before you start coding:

1. **Quote Reader Protocol:** Implement a new `QuoteReader` protocol and `HttpQuoteReader` client rather than bloating the existing `HttpQuoteCreator` (ISP principle).
2. **Three Endpoints:** Keep pricing analysis, missing items, and rewrite as three separate HTTP POST endpoints to maintain distinct prompt templates and allow parallel frontend calls.
3. **Claude Sonnet 5 for Copilot:** The plan maps settings to use `"claude-sonnet-5"` for copilot requests (`Settings.copilot_model`). This balances high quality formatting with a 40% cost reduction compared to Opus 5.

---

## Step 4 — Implement

### Implementation Order

1. **Domain Extensions** — Add `AiFeature.COPILOT` to the enum, and define data models/protocols/errors in `models.py`, `protocols.py`, and `errors.py`.
2. **Application Use Cases** — Create `copilot_pricing.py`, `copilot_missing.py`, and `copilot_rewrite.py`.
3. **Infrastructure Clients & Adapters** — Build `quote_reader.py` (fetching GET quote details via `ServiceClient`), `copilot_claude_adapter.py` (Sonnet 5 structured outputs), and the prompt templates under `prompts/`.
4. **Interface routes/schemas** — Add DTOs to `schemas.py` and register the three `/copilot/*` routes in `routes.py`. Ensure composition in `deps.py`.
5. **Config update** — Add settings in `config.py` (`copilot_model`, `feature_copilot`).
6. **Tests** — Create the 8 test files mapping to use cases, prompts, margin arithmetic, and routes.
7. **Verification** — Ensure all checks pass cleanly.

---

## Step 5 — Update Tracker

When done:
1. Check the box in `TASKS.md`: `- [x] T202 ...`
2. Update `tracking/PROGRESS-TRACKER.csv`: status → `DONE`, fill end date.

---

## Step 6 — Definition of Done

- [ ] 3 endpoints working (`/copilot/analyze-pricing`, `/copilot/missing-items`, `/copilot/rewrite`).
- [ ] Metered usage logged under `feature: "copilot"` with model token costs.
- [ ] Margin arithmetic is done programmatically, not delegated to the LLM.
- [ ] `ruff check app tests` — clean.
- [ ] `mypy app` — clean.
- [ ] `pytest tests/` — all 128+ tests pass, ≥80% coverage on new logic.
- [ ] `python scripts/check_conventions.py` — green.
- [ ] Doc `docs/modules/M16-ai-copilot.md` completed.

---

**Begin now. Read `docs/modules/M16-ai-copilot-plan.md` first, then start coding.**
