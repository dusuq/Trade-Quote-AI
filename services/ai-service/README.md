# AI Service (Module M15 / T201)

- **Owner Agent:** Agent 1 (NLP/copilot) / Agent 3 (vision/OCR — T304–T306, not yet built)
- **Bounded Context / Purpose:** All AI capabilities
- **Depends on:** T106 Quote Engine, T105 Pricebook
- **Plan:** [M15 plan](../../docs/modules/M15-ai-quote-assistant-plan.md) · **Spec:** [M15 spec](../../docs/modules/M15-ai-quote-assistant.md)

A contractor speaks or types a job description; the service transcribes it, extracts a structured
scope, matches each item against the tenant's own pricebook, and creates a draft quote.

## What's built (T201)

- **Voice and text entry points** converging on one pipeline — once audio becomes text the flows are
  identical, so they share an implementation rather than drifting apart.
- **Structured-output scope extraction** (`claude-opus-5`) — the response is constrained to a JSON
  schema, so there is no "reply with JSON only" pleading and no brace-counting parser.
- **Pricebook matching** with an explicit confidence floor: below it a task becomes a $0 line the
  contractor prices by hand, rather than a plausible-looking wrong price.
- **Scope writer** — structured scope to customer-facing prose.
- **Metering** — every call writes to `ai_usage_log`, with an optional per-tenant daily spend cap
  enforced *before* the model runs.

Still to come: AI Vision (T304), OCR (T305), Sales Coach (T306), full Copilot (T202).

## Architecture

```
app/
├── domain/          entities, ports, events, errors — no I/O
├── application/     use cases + the pure logic worth testing hardest:
│                      line_items.py  money/markup mapping (conventions §5)
│                      matching.py    pricebook match scoring
│                      audio.py       upload validation
├── infrastructure/  Claude + Whisper adapters, shared HTTP client, DB, costs
└── interface/       DTOs, routes, and the composition root (`deps.py`)
```

Runs on port **8008**; reachable through the gateway at `/v1/ai`.

## HTTP surface

| Method | Path | |
| --- | --- | --- |
| POST | `/v1/ai/text-to-quote` | typed description → draft quote |
| POST | `/v1/ai/voice-to-quote` | `multipart/form-data` audio → draft quote |
| POST | `/v1/ai/scope-writer` | structured scope → customer-facing prose |
| GET | `/v1/ai/usage` | this tenant's metered AI calls |

## Two decisions worth knowing

**Pricing lives in quote-service, not here.** `LineItemCreate.unit_price_minor` is documented as
derived from `unit_cost_minor * (1 + markup_bps/10000)` when omitted, so this service sends cost and
markup and never computes a price — a second implementation of that arithmetic is a second thing
that can drift. When a pricebook item carries its own `default_markup_bps`, that wins over the
request-level default: a tenant who priced conduit at 15% meant 15%.

**Sync HTTP is used deliberately, under [ADR-0003](../../docs/adr/ADR-0003-sync-service-to-service-http.md).**
Pricebook lookup and quote creation are on the critical path — without them there is no answer to
return. Every such call goes through `infrastructure/http.py`, which enforces timeouts, retries only
on retryable failures, and never replays a POST after a timeout (that could create the quote twice).
Network calls never run inside an open database transaction: usage is buffered and written in a short
transaction afterwards.

## Develop

```bash
uv run --project services/ai-service pytest services/ai-service/tests
```

Needs `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` at runtime. **Tests need neither** — every adapter sits
behind a Protocol with an in-memory fake, so the suite makes no network calls.

## Definition of Done

- ✅ Clean Architecture layering (domain → application → infrastructure → interface)
- ✅ Events consumed from `packages/types` (`ai.quote.drafted`, `ai.usage.recorded`) — not reinvented
- ✅ Tenant-scoped (`tenant_id` + RLS in `0009_ai_service.sql`), with an isolation test
- ✅ Money as integer minor units, rates as basis points — asserted in tests
- ✅ No `import jwt` anywhere; trusts the gateway's `x-tenant-id`
- ✅ ruff / mypy / pytest clean; `check_conventions.py` OK
- ⬜ Web UI — tracked as **T201b**

## Known limitations (deliberately explicit)

- **No web UI** — **T201b**, the same standard applied to T204b and T307b.
- **`created_via` for typed input is recorded as `manual`.** `QuoteCreatedVia` has no value meaning
  "AI drafted this from typed text". Rather than mislabel it `voice` or unilaterally widen a contract
  two other services share, the AI provenance rides on `ai.quote.drafted.inputKind` and the
  `ai_usage_log` row. Adding a proper enum value is a follow-up.
- **Never run against live Postgres** — the RLS policy is Postgres-only and untestable under the
  SQLite harness. Folded into **T311**.
- **No idempotency key.** A retried `voice-to-quote` creates a second draft quote. The plan called
  for `x-idempotency-key`; it needs a dedupe store to be real, so it is scoped out rather than
  half-built.
- Chunked transcription for recordings over the 10 MB / ~5 min cap is post-MVP.
