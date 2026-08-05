# T202b — M16 AI Copilot Web UI — Design

**Status:** Draft for review · **Owner:** Agent 2 (Sonnet 5) · **Depends on:** T202 (done, signed off)

## 1. Problem

T202 shipped three read-only advisory endpoints under `/v1/ai/copilot/*`
(`analyze-pricing`, `missing-items`, `rewrite`) on `services/ai-service`, fully
tested and gateway-reachable — but nothing in `apps/web` calls them. T202b
wires them into the quote detail page so a contractor can ask the copilot
"how's my pricing?", "what am I missing?", and "make this description sound
professional?" against a quote they've already created.

## 2. Scope

**In scope:** a Copilot panel on the quote detail page
(`apps/web/src/app/(app)/quotes/[id]/page.tsx`) offering pricing analysis and
missing-items detection on demand, plus an inline "rewrite" action on each
line item's description.

**Out of scope:** any change to the quote builder (`quotes/new`). The
copilot backend only accepts an existing `quote_id` (it reads the quote via
`GET /v1/quotes/{id}`); the builder is a single-shot form with no quote ID
until after creation, at which point it already redirects to the detail
page — so copilot is one save away from every new quote with no flow change
needed. Restructuring quote creation into a two-step draft-then-edit flow to
support live analysis mid-build is a separate, larger effort and not part of
this task.

## 3. Backend contract (T202, unchanged — reference only)

```
POST /v1/ai/copilot/analyze-pricing
  body: { quote_id: UUID }
  200: { quote_id, suggestions: [{ line_item_id, current_unit_cost_minor,
         current_markup_bps, current_unit_price_minor,
         suggested_markup_bps: int|null, pricebook_unit_cost_minor: int|null,
         reasoning }], margin: { total_cost_minor, total_revenue_minor,
         gross_margin_bps, average_markup_bps, low_margin_item_ids: UUID[],
         recommendation }, model_id, tokens_used }
  errors: 400 bad UUID · 401 no tenant · 404 quote not found ·
          422 LLM failure · 429 spend cap · 502 upstream down ·
          503 copilot disabled

POST /v1/ai/copilot/missing-items
  body: { quote_id: UUID, job_description?: string }
  200: { quote_id, trade, completeness_score: int (0-100), summary,
         missing: [{ description, category: "material"|"labor"|"equipment",
         item_name, estimated_quantity: Decimal, unit, reasoning,
         priority: "critical"|"recommended"|"optional" }], model_id,
         tokens_used }
  errors: same set as analyze-pricing

POST /v1/ai/copilot/rewrite
  body: { texts: string[], tone?: string, context_hint?: string }
  200: { rewritten: string[] (1:1 with texts), model_id, tokens_used }
  errors: 400/422 empty or count-mismatched texts · 401 · 429 · 503
```

Quote-service (unchanged, existing routes used to apply suggestions):

```
PUT /v1/quotes/{quote_id}/line-items/{line_item_id}
  body (all optional, partial update): { description?, kind?, quantity?,
    unit?, unit_cost_minor?, markup_bps?, unit_price_minor?, is_optional?,
    sort_order? }
  Sending markup_bps alone recomputes unit_price_minor server-side
  (unit_cost_minor * (1 + markup_bps/10000)) and recalculates quote totals —
  confirmed in services.py::update_line_item. No web-side price math needed.

POST /v1/quotes/{quote_id}/line-items
  body: { description, kind, quantity, unit, unit_cost_minor: 0,
    markup_bps: 0, unit_price_minor: 0, ... }
  Used to add an accepted missing item as a new line, priced at 0 — the
  contractor fills in cost/price by hand afterward, the same convention
  T201b established for AI-matched-but-unpriced tasks.
```

## 4. Data layer — `apps/web/src/lib/copilot.ts` (new file)

TypeScript types mirror the backend DTOs field-for-field:

```typescript
export interface PricingSuggestion {
  line_item_id: string;
  current_unit_cost_minor: number;
  current_markup_bps: number;
  current_unit_price_minor: number;
  suggested_markup_bps: number | null;
  pricebook_unit_cost_minor: number | null;
  reasoning: string;
}

export interface MarginAnalysis {
  total_cost_minor: number;
  total_revenue_minor: number;
  gross_margin_bps: number;
  average_markup_bps: number;
  low_margin_item_ids: string[];
  recommendation: string;
}

export interface PricingAnalysisResult {
  quote_id: string;
  suggestions: PricingSuggestion[];
  margin: MarginAnalysis;
  model_id: string;
  tokens_used: number;
}

export type MissingItemCategory = "material" | "labor" | "equipment";
export type MissingItemPriority = "critical" | "recommended" | "optional";

export interface MissingItem {
  description: string;
  category: MissingItemCategory;
  item_name: string;
  estimated_quantity: number;
  unit: string;
  reasoning: string;
  priority: MissingItemPriority;
}

export interface MissingItemsResult {
  quote_id: string;
  trade: string;
  completeness_score: number;
  summary: string;
  missing: MissingItem[];
  model_id: string;
  tokens_used: number;
}

export interface CopilotRewriteResult {
  rewritten: string[];
  model_id: string;
  tokens_used: number;
}
```

Functions (all reuse `ai.ts`'s exported `AI_REQUEST_TIMEOUT_MS` — 90s, same
rationale: these are LLM calls that can legitimately outrun the default 10s
`apiFetch` timeout):

- `analyzePricing(token: string, quoteId: string): Promise<PricingAnalysisResult>`
  → `POST /v1/ai/copilot/analyze-pricing`, body `{ quote_id: quoteId }`.
- `findMissingItems(token: string, quoteId: string, jobDescription?: string): Promise<MissingItemsResult>`
  → `POST /v1/ai/copilot/missing-items`, body `{ quote_id: quoteId, job_description: jobDescription || undefined }`.
- `rewriteTexts(token: string, texts: string[], tone?: string, contextHint?: string): Promise<CopilotRewriteResult>`
  → `POST /v1/ai/copilot/rewrite`, body `{ texts, tone: tone ?? "professional", context_hint: contextHint }`.
- `addMissingItemToQuote(token: string, quoteId: string, item: MissingItem): Promise<LineItem>`
  → `POST /v1/quotes/{quoteId}/line-items`, body `{ description: item.description, kind: missingItemCategoryToItemKind(item.category), quantity: item.estimated_quantity, unit: item.unit, unit_cost_minor: 0, markup_bps: 0, unit_price_minor: 0 }`.
  This calls the raw quote-service endpoint directly (not `quotes.ts`'s
  `addLineItem`, which hardcodes `kind` to the server default and is built
  around the dollar-input form schema, not a decimal quantity from an AI
  response).
- `applyMarkupSuggestion(token: string, quoteId: string, lineItemId: string, markupBps: number): Promise<LineItem>`
  → `PUT /v1/quotes/{quoteId}/line-items/{lineItemId}`, body `{ markup_bps: markupBps }`.

Pure helpers (unit-tested, no I/O):

- `missingItemCategoryToItemKind(category: MissingItemCategory): LineItem["kind"]`
  — direct passthrough; the three category values are already valid
  `ItemKind` values on the quote-service side.
- `priorityBadgeVariant(priority: MissingItemPriority): "destructive" | "warning" | "secondary"`
  — `critical` → `destructive`, `recommended` → `warning`, `optional` → `secondary`.

`apps/web/src/lib/ai.ts` changes:

- Export the existing `AI_REQUEST_TIMEOUT_MS` constant (currently module-private) so `copilot.ts` reuses it instead of duplicating the value.
- `describeAiSubmitError` gets one new `case 503:` → `"AI Copilot is currently disabled."` (currently falls through to the generic default message for every disabled-feature response, copilot's `_require_copilot()` 503 included).

## 5. UI — `CopilotPanel` component + inline rewrite

New file `apps/web/src/components/ai/copilot-panel.tsx`. Props: `{ token: string; quote: Quote }`. Rendered on the quote detail page below the existing Line Items card. One `Card` titled "AI Copilot" containing two independent on-demand sections — nothing runs automatically, since every call is metered against the tenant's daily spend cap:

**Pricing section**

- "Analyze Pricing" button → `useMutation(() => analyzePricing(token, quote.id))`.
- On success, renders:
  - The margin block: total cost / total revenue / gross margin % (`gross_margin_bps / 100`) / average markup % / the `recommendation` string.
  - A list of `suggestions`, each matched to `quote.line_items` by `line_item_id` (a direct ID lookup — no order-based guessing, since T202's response carries real IDs, unlike T201's index-based matching this app already has a workaround for). Each row shows current vs. suggested markup and `reasoning`. A line whose ID is in `margin.low_margin_item_ids` gets a "Low margin" destructive badge.
  - Each suggestion with a non-null `suggested_markup_bps` gets its own "Apply" button — a separate `useMutation(() => applyMarkupSuggestion(token, quote.id, suggestion.line_item_id, suggestion.suggested_markup_bps))` that invalidates `["quotes", quote.id]` on success. Kept as a separate mutation per-suggestion (not batched) so one apply failing doesn't block others, and a failed apply never clears the already-fetched analysis (no need to re-spend on a fresh AI call to retry).

**Missing Items section**

- An optional `<textarea>` for `job_description` (matches the backend's optional field — better completeness-detection context when filled, not required).
- "Find Missing Items" button → `useMutation(() => findMissingItems(token, quote.id, jobDescription))`.
- On success, renders `completeness_score` (e.g. "72/100"), `summary`, and each `missing` item with its `priority` badge (via `priorityBadgeVariant`), `reasoning`, and estimated quantity/unit.
- Each missing item gets an "Add to Quote" button — `useMutation(() => addMissingItemToQuote(token, quote.id, item))` that invalidates `["quotes", quote.id]` on success. Independent per-item mutation, same rationale as the pricing Apply buttons.

**Inline rewrite (not part of `CopilotPanel` — lives in the existing line-items table)**

- In `quotes/[id]/page.tsx`'s line-items table, add a small pencil icon-button next to each row's description.
- Clicking it opens an inline `<textarea>` (replacing the plain description cell for that row) pre-filled with the current description, plus "Rewrite" and "Cancel" buttons.
- "Rewrite" → `useMutation(() => rewriteTexts(token, [currentText]))`. On success, the textarea's content is replaced with `rewritten[0]` — the contractor can keep editing, then either "Save" (→ `PUT /v1/quotes/{id}/line-items/{id}` with `{ description: newText }`, invalidate, close the inline editor) or "Cancel" (discard, close). The rewrite is never auto-applied — matches T201b's established "no auto-anything on AI output" principle.
- This needs one small new component, `apps/web/src/components/ai/inline-rewrite-editor.tsx`, taking `{ token, quoteId, lineItemId, initialText, onSaved, onCancel }` so the row-rendering logic in the page stays simple (open/closed state keyed by line item ID).

## 6. Error handling

Every mutation's `onError` calls `describeAiSubmitError(err)` (imported from `ai.ts`) for the user-facing message, covering 429 (spend cap), 502 (upstream down), 422 (LLM failure), and now 503 (copilot disabled). Analysis mutations (`analyzePricing`, `findMissingItems`) and apply/add mutations are kept as separate `useMutation` instances so a failure in one never clears a successful result from the other — critically, a failed "Apply" or "Add to Quote" doesn't discard the AI analysis that's already been paid for, so the contractor can just retry the write without re-running the (metered) AI call.

## 7. Testing

- `apps/web/src/lib/copilot.test.ts` (new): unit tests for `missingItemCategoryToItemKind`, `priorityBadgeVariant`, and the four fetch-wrapper functions (request shape — method, path, body — mirroring the existing style in `ai.test.ts`).
- No backend or gateway test changes: T202's 185 ai-service tests and the gateway's existing `/v1/ai` proxy (already handling POST JSON bodies since T201/T201b) are unchanged by this UI-only task.
- Live verification: exercise all three copilot actions plus apply/add/rewrite-save against a running quote in the browser before calling the task done.

## 8. Global constraints (carried into the implementation plan)

- Money stays in integer minor units end-to-end; never convert to dollars except at display (`formatMoney`) or in the existing dollar-input form schema (untouched by this task).
- No client-side margin/markup arithmetic — every number displayed comes from the backend response; the web layer only renders and forwards `suggested_markup_bps` back to quote-service verbatim.
- Every new AI-calling mutation uses `AI_REQUEST_TIMEOUT_MS` (90s), not the 10s default.
- No auto-apply of any AI suggestion — every apply/add/rewrite-save is an explicit contractor click.
