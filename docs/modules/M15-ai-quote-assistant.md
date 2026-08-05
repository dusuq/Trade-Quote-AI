# T201 — M15 AI Quote Assistant · Design Spec

| Field            | Value                                                             |
| ---------------- | ----------------------------------------------------------------- |
| **Task**         | `T201`                                                            |
| **Module**       | M15 — AI Quote Assistant (voice→text→structured scope→line items) |
| **Owner agent**  | Agent 1 (CTO)                                                     |
| **Phase**        | Phase 2 — AI + Delivery                                           |
| **Dependencies** | `T106` Quote Engine ✅, `T105` Pricebook ✅                       |
| **Unblocks**     | `T202` AI Copilot; `T304`/`T305`/`T306` Vision/OCR/Sales Coach    |
| **Date**         | 2026-07-28                                                        |
| **Bounded ctx**  | `services/ai-service` (new, port 8008)                            |
| **Plan**         | [M15 plan](M15-ai-quote-assistant-plan.md) (Agent 3)              |

---

## 1. Problem

Quoting is the bottleneck this product exists to remove. A contractor finishes a site visit, then
spends 30 minutes turning notes into a priced quote — looking every item up in their pricebook by
hand. The wedge is doing that in two minutes from a spoken description.

Everything needed already exists separately: T106 creates quotes and computes prices, T105 holds the
tenant's catalog. Nothing turns _"replace the panel with a 200 amp and put twelve LED cans in"_ into
the structured, priced line items those services want.

---

## 2. Decisions

### D1 — Two entry points, one pipeline

`/voice-to-quote` and `/text-to-quote` differ only in whether a transcription step runs first. Once
audio becomes text the flows are identical, so `VoiceToQuoteUseCase` composes `TextToQuoteUseCase`
rather than duplicating it. Forking them would let the voice path silently drift out of sync with
the text path's matching and pricing behavior.

### D2 — Structured outputs, not prompt-and-pray

Scope extraction uses the Messages API's `output_config.format` with a JSON schema. The model's
response is constrained to the schema, so there is no "reply with JSON only" instruction to be
ignored and no brace-counting parser to break.

The schema constrains _shape_; `parse_scope` still validates _semantics_ — a quantity of `0`
satisfies `{"type": "number"}` and is not a billable line item.

### D3 — Corrections to the plan's model configuration

The plan specified `claude-sonnet-4-20250514` with `temperature: 0.1`. Both are wrong against the
current API and were changed:

- **Model → `claude-opus-5`.** The planned ID is superseded. Extraction quality here directly
  determines whether a contractor trusts the output, so this is not the place to economize.
- **`temperature` removed entirely.** Current models **reject** `temperature`/`top_p`/`top_k` with a 400. The plan's intent (deterministic extraction) is served by the constrained output schema.

### D4 — Pricing stays in quote-service

`LineItemCreate.unit_price_minor` is documented as derived from
`unit_cost_minor * (1 + markup_bps/10000)` when omitted. So ai-service sends **cost and markup, never
a price**. A second implementation of that arithmetic is a second thing that can drift out of sync,
and money that disagrees between two services is the worst kind of bug to debug.

When a matched pricebook item carries its own `default_markup_bps`, it wins over the request-level
default — a tenant who priced conduit at 15% and service calls at 60% meant those numbers.

### D5 — A confidence floor, and unmatched items survive

Match scoring (`application/matching.py`) is pure and ranks exact SKU > exact name > substring >
token overlap. Below `MIN_CONFIDENCE` the result is **no match**, not a best guess: a plausible wrong
price attached to a real line item is much harder for a contractor to notice than an obvious $0 line
asking to be filled in.

Unmatched tasks are **never dropped**. They become zero-cost line items, because silently discarding
scope the customer described is worse than surfacing it unpriced.

### D6 — ADR-0003: sync HTTP, but only on the critical path

This task needed the codebase's first sanctioned service-to-service HTTP calls, which T203 had
deliberately declined to introduce and T307b had introduced badly. [ADR-0003](../adr/ADR-0003-sync-service-to-service-http.md)
resolves both cases with one test: _if this call fails, is the user's request still meaningfully
complete?_ No → sync HTTP (pricebook, quote creation). Yes → outbox (analytics).

All such calls go through one shared client that enforces timeouts, retries only retryable failures,
and **never replays a POST after a timeout** — replaying `POST /v1/quotes` could create the quote
twice.

### D7 — Metering, and the transaction discipline it forced

Every AI call writes to `ai_usage_log`, with an optional per-tenant daily spend cap checked _before_
the model runs (a cost control that fires after you've spent the money isn't one).

That collided with ADR-0003 rule 3 — no network I/O inside an open transaction. Resolved by
`BufferedAiUsageRepository`: read spend-to-date in one short transaction, run the pipeline with
nothing open, write buffered usage in another. Same data, no pooled connection pinned across an LLM
call.

### D8 — Backend only

No web UI, matching the T204/T204b and T307/T307b pattern. Tracked as **T201b**.

---

## 3. HTTP surface

All routes authenticated; the gateway supplies `x-tenant-id`. No public routes.

| Method | Path                    | Notes                                                |
| ------ | ----------------------- | ---------------------------------------------------- |
| POST   | `/v1/ai/text-to-quote`  | 201 → draft quote + extracted scope                  |
| POST   | `/v1/ai/voice-to-quote` | `multipart/form-data`; 413 oversized, 400 bad format |
| POST   | `/v1/ai/scope-writer`   | structured scope → prose                             |
| GET    | `/v1/ai/usage`          | this tenant's metered calls                          |

Errors: `401` no tenant · `422` unusable scope · `429` spend cap · `502` upstream/AI failure.

---

## 4. Data

`0009_ai_service.sql` adds **`ai_usage_log`** only — the service owns no quote or pricebook tables,
since it reaches those over HTTP. RLS mirrors the established pattern.

`feature`/`model_id`/`input_kind` are `text`, not Postgres enums: this is append-only billing
telemetry that must keep accepting rows when a new model ships, and requiring a schema migration
before a usage record can be written is a poor gate. It also sidesteps the T206b `values_callable`
trap entirely.

---

## 5. Verification

| Check                                       | Result                                                    |
| ------------------------------------------- | --------------------------------------------------------- |
| `ai-service` pytest                         | **120/120**                                               |
| `ai-service` ruff / mypy                    | clean                                                     |
| Gateway vitest                              | **26/26** (up from 25 — added a `/v1/ai` auth+proxy test) |
| All 8 backend services (`run_all_tests.py`) | pytest/ruff/mypy green                                    |
| `check_conventions.py`                      | OK                                                        |

No test makes a network call or needs an API key — every adapter sits behind a Protocol with an
in-memory fake.

---

## 6. Known gaps (tracked, not silently dropped)

1. **No web UI** → **T201b**.
2. **`created_via` for typed input is `manual`.** `QuoteCreatedVia` has no value meaning "AI drafted
   this from typed text". Rather than mislabel it `voice` or unilaterally widen a contract two other
   services share, provenance rides on `ai.quote.drafted.inputKind` and the usage row. Adding a
   proper enum value needs Agent 2's quote-service and `packages/types` together.
3. **No idempotency key.** The plan called for `x-idempotency-key`; making it real needs a dedupe
   store, so it is scoped out rather than half-built. A retried `voice-to-quote` creates a second
   draft quote today.
4. **Never run against live Postgres** — the RLS policy is Postgres-only and untestable under the
   SQLite harness. Folded into **T311**.
5. **Prompt quality is unmeasured.** Extraction correctness is asserted against fakes; no eval set
   scores real transcripts yet. That belongs with M25's test/eval work.
