# M16 — AI Copilot (T202)

**Status:** ✅ Done · **Owner:** Agent 1 (CTO / Opus 4.8) · **Service:** `services/ai-service`
**Deps:** T106 (Quote Engine), T201 (AI Quote Assistant) · **Unblocks:** T304, T305, T306

The AI Copilot is the advisory layer that sits alongside an existing quote. Unlike T201 (which
_creates_ a quote), the copilot _reads_ a quote and returns advice — it never mutates anything. Three
endpoints answer the four questions contractors ask:

| Question                                                   | Endpoint                              |
| ---------------------------------------------------------- | ------------------------------------- |
| 💰 How much should I charge? / 📈 Can I improve my margin? | `POST /v1/ai/copilot/analyze-pricing` |
| 🔍 What's missing?                                         | `POST /v1/ai/copilot/missing-items`   |
| ✏️ Rewrite this professionally                             | `POST /v1/ai/copilot/rewrite`         |

All three are proxied under the existing `/v1/ai` gateway route (added in T201) — no gateway change.

## API contract

### `POST /v1/ai/copilot/analyze-pricing`

- **Body:** `{ "quote_id": "<UUID>" }`
- **200:** `PricingAnalysisResponse` — per-line `suggestions` (current vs. suggested markup, pricebook
  cost, reasoning) + a quote-level `margin` block.
- **Errors:** `400` bad UUID · `401` no tenant · `404` quote not found · `422` LLM failure ·
  `429` spend cap · `502` upstream down · `503` copilot disabled.

### `POST /v1/ai/copilot/missing-items`

- **Body:** `{ "quote_id": "<UUID>", "job_description": "<optional>" }`
- **200:** `MissingItemsResponse` — `missing[]` (category, item_name, estimated_quantity, priority,
  reasoning), `trade`, `completeness_score` (0–100), `summary`.
- **Errors:** same set as analyze-pricing.

### `POST /v1/ai/copilot/rewrite`

- **Body:** `{ "texts": [...], "tone": "professional", "context_hint": "<optional>" }`
- **200:** `RewriteResponse` — `rewritten[]`, 1:1 with the input texts.
- **Errors:** `400`/`422` empty or count-mismatched texts · `401` · `429` · `503`.

## Key design decisions

1. **Read-only.** The copilot never writes to quote-service. Every suggestion goes back to the client
   for the contractor to apply by hand — no risk of AI silently changing a quote, and no new
   service-to-service write path.
2. **Margin math is local, not LLM.** Gross margin = `(revenue − cost) / revenue × 10000` bps is pure
   integer arithmetic in [`application/margin.py`](../../services/ai-service/app/application/margin.py).
   The LLM supplies _reasoning and markup suggestions only_; every number comes from the quote's own
   data. `test_margin_math.py` covers this exhaustively with no LLM in the loop.
3. **Sonnet 5 for copilot** (`Settings.copilot_model`), vs. Opus 5 for T201's scope extraction.
   Copilot output is advisory prose + suggestions, not schema-critical extraction, so the ~40%-cheaper,
   faster tier is the right trade-off. Falls back to Opus only if quality proves insufficient.
4. **Separate `QuoteReader` port** (`HttpQuoteReader`) rather than extending `HttpQuoteCreator` (ISP):
   read and write concerns stay separated, and a "creator" that also reads would be misleading. Both
   share the one `ServiceClient` per ADR-0003; `GET /v1/quotes/{id}` is idempotent and safe to retry.
5. **Trade-specific prompts.** The missing-items prompt embeds per-trade checklists (electrical:
   breakers/conduit/ground rod/permit; plumbing: fittings/valves; HVAC: refrigerant/condensate; etc.)
   — the core value a generic model wouldn't have.

## Architecture (Clean Architecture, per conventions §3)

```
domain/         AiFeature.COPILOT + QuoteSnapshot/QuoteLineItem/PricingSuggestion/
                MarginAnalysis/MissingItem/… value objects; QuoteReader/CopilotAnalyzer/
                TextRewriter ports; QuoteNotFoundError/CopilotAnalysisError
application/    margin.py (pure math) · AnalyzePricingUseCase · FindMissingItemsUseCase ·
                RewriteUseCase  (orchestration only, depend on ports)
infrastructure/ HttpQuoteReader · ClaudeCopilotAnalyzer + ClaudeTextRewriter (Sonnet 5,
                structured outputs) · prompts/copilot_{pricing,missing,rewrite}.py
interface/      copilot DTOs + mappers · /copilot/* routes · deps factories
```

Money stays in integer minor units, rates in basis points, quantities in `Decimal` (conventions §5).
No JWT decode — the routes trust the gateway's `x-tenant-id`/`x-user-id` headers (conventions §1).
Metered usage is logged under `feature: "copilot"` with model token cost, matching the canonical
`AiUsageRecordedPayload` in `packages/types`.

## Verification

- `ruff check app tests` — clean
- `mypy app` — clean
- `pytest tests/` — **185 passed** (120 T201 regression + 65 new)
- `python scripts/check_conventions.py` — green
- Coverage on new application/domain logic: **95–100%** (97% across the copilot surface)

New tests: `test_margin_math`, `test_copilot_pricing`, `test_copilot_missing`, `test_copilot_rewrite`,
`test_quote_reader`, `test_copilot_prompts`, `test_copilot_schemas`, `test_copilot_routes`, plus
`test_copilot_adapter` (adapter orchestration via an injected fake SDK client).
