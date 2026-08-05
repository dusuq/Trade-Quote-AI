# T202b M16 AI Copilot Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire T202's three read-only `/v1/ai/copilot/*` endpoints into the quote detail page — an on-demand pricing analysis + apply flow, an on-demand missing-items check + add-to-quote flow, and an inline per-line "rewrite professionally" action.

**Architecture:** One new data-layer file (`lib/copilot.ts`) with typed fetch wrappers matching the backend DTOs exactly, one new `CopilotPanel` component holding the two on-demand analysis sections, and one new `InlineRewriteEditor` component wired into the existing line-items table. All writes (apply markup, add missing item, save rewritten description) go through quote-service's existing `PUT`/`POST` line-item routes directly — the copilot backend itself is never asked to write anything.

**Tech Stack:** Next.js 15 App Router, TanStack Query, vitest, existing `apps/web/src/components/ui/*` primitives (Card, Badge, Button), `lucide-react` icons.

## Global Constraints

- Money stays in integer minor units end-to-end; convert to dollars only at display via `formatMoney` (never in this task's new code).
- No client-side margin/markup arithmetic — every number shown comes verbatim from the backend response.
- Every new AI-calling mutation (`analyzePricing`, `findMissingItems`, `rewriteTexts`) uses the existing `AI_REQUEST_TIMEOUT_MS` (90,000 ms), not `apiFetch`'s 10s default.
- No auto-apply of any AI suggestion — applying a markup, adding a missing item, and saving a rewrite are each an explicit contractor click, never automatic on the analysis response.
- No component test files — this codebase's established pattern (T201b: `voice-recorder.tsx`, `ai-draft-banner.tsx`, `write-scope-panel.tsx`) is unit tests only for pure functions/data-layer files in `lib/*.ts`; UI components are verified live in the browser, not via `.test.tsx` files. Do not introduce one.
- Follow the existing `write-scope-panel.tsx` interaction pattern: a button triggers a `useMutation`, errors render via `describeAiSubmitError`, results render inline in the same component — no modals, no drawers.

---

### Task 1: `ai.ts` — export the AI timeout constant, add a 503 case to `describeAiSubmitError`

**Files:**

- Modify: `apps/web/src/lib/ai.ts:73` and `apps/web/src/lib/ai.ts:170-188`
- Modify: `apps/web/src/lib/ai.test.ts` (add one test to the existing `describeAiSubmitError` describe block)

**Interfaces:**

- Consumes: nothing new.
- Produces: `export const AI_REQUEST_TIMEOUT_MS = 90_000` (was module-private `const`) — Task 2's `copilot.ts` imports this. `describeAiSubmitError` gains a `503` case.

- [ ] **Step 1: Export the timeout constant**

In `apps/web/src/lib/ai.ts`, change line 73 from:

```typescript
const AI_REQUEST_TIMEOUT_MS = 90_000;
```

to:

```typescript
export const AI_REQUEST_TIMEOUT_MS = 90_000;
```

- [ ] **Step 2: Write the failing test for the new 503 case**

In `apps/web/src/lib/ai.test.ts`, inside the existing `describe("describeAiSubmitError", ...)` block, add a new `it`:

```typescript
it("maps 503 to a copilot-disabled message", () => {
  expect(describeAiSubmitError(new ApiError(503, "x"))).toBe("AI Copilot is currently disabled.");
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd apps/web && pnpm vitest run src/lib/ai.test.ts`
Expected: FAIL — the new assertion gets `"Request failed with status 503"` (or the raw message `"x"` doesn't match since `err.message` for `ApiError(503, "x")` is `"x"`, which isn't `"AI Copilot is currently disabled."`).

- [ ] **Step 4: Add the 503 case**

In `apps/web/src/lib/ai.ts`, change the `describeAiSubmitError` switch (currently lines 170-188) from:

```typescript
export function describeAiSubmitError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 413:
        return "That recording is too long. Try a shorter one.";
      case 400:
        return "That audio format isn't supported. Try recording again.";
      case 429:
        return "You've reached today's AI usage limit. Try again tomorrow.";
      case 502:
        return "The AI service is temporarily unavailable. Try again shortly.";
      case 422:
        return "Couldn't make sense of that description — try adding more detail.";
      default:
        return err.message || "Something went wrong. Please try again.";
    }
  }
  return "Something went wrong. Please try again.";
}
```

to:

```typescript
export function describeAiSubmitError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 413:
        return "That recording is too long. Try a shorter one.";
      case 400:
        return "That audio format isn't supported. Try recording again.";
      case 429:
        return "You've reached today's AI usage limit. Try again tomorrow.";
      case 502:
        return "The AI service is temporarily unavailable. Try again shortly.";
      case 422:
        return "Couldn't make sense of that description — try adding more detail.";
      case 503:
        return "AI Copilot is currently disabled.";
      default:
        return err.message || "Something went wrong. Please try again.";
    }
  }
  return "Something went wrong. Please try again.";
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd apps/web && pnpm vitest run src/lib/ai.test.ts`
Expected: PASS — all tests in the file (the pre-existing ones plus the new one) pass.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/ai.ts apps/web/src/lib/ai.test.ts
git commit -m "feat: export AI_REQUEST_TIMEOUT_MS and map 503 to a copilot-disabled message"
```

---

### Task 2: `copilot.ts` data layer

**Files:**

- Create: `apps/web/src/lib/copilot.ts`
- Test: `apps/web/src/lib/copilot.test.ts`

**Interfaces:**

- Consumes: `AI_REQUEST_TIMEOUT_MS` from `@/lib/ai` (Task 1), `apiFetch` from `@/lib/api-client`, `LineItem` from `@/lib/quotes`.
- Produces (consumed by Task 3 and Task 4): types `PricingSuggestion`, `MarginAnalysis`, `PricingAnalysisResult`, `MissingItemCategory`, `MissingItemPriority`, `MissingItem`, `MissingItemsResult`, `CopilotRewriteResult`; functions `analyzePricing(token: string, quoteId: string): Promise<PricingAnalysisResult>`, `findMissingItems(token: string, quoteId: string, jobDescription?: string): Promise<MissingItemsResult>`, `rewriteTexts(token: string, texts: string[], tone?: string, contextHint?: string): Promise<CopilotRewriteResult>`, `addMissingItemToQuote(token: string, quoteId: string, item: MissingItem): Promise<LineItem>`, `applyMarkupSuggestion(token: string, quoteId: string, lineItemId: string, markupBps: number): Promise<LineItem>`, `updateLineItemDescription(token: string, quoteId: string, lineItemId: string, description: string): Promise<LineItem>`; pure helpers `missingItemCategoryToItemKind(category: MissingItemCategory): LineItem["kind"]`, `priorityBadgeVariant(priority: MissingItemPriority): "destructive" | "warning" | "secondary"`, `formatBpsPercent(bps: number): string`.

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/lib/copilot.test.ts`:

```typescript
// apps/web/src/lib/copilot.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  addMissingItemToQuote,
  analyzePricing,
  applyMarkupSuggestion,
  findMissingItems,
  formatBpsPercent,
  missingItemCategoryToItemKind,
  priorityBadgeVariant,
  rewriteTexts,
  updateLineItemDescription,
  type MissingItem,
} from "@/lib/copilot";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(body),
    }),
  );
}

const SAMPLE_PRICING_RESULT = {
  quote_id: "22222222-2222-2222-2222-222222222222",
  suggestions: [],
  margin: {
    total_cost_minor: 10000,
    total_revenue_minor: 15000,
    gross_margin_bps: 3333,
    average_markup_bps: 5000,
    low_margin_item_ids: [],
    recommendation: "Margins look healthy.",
  },
  model_id: "claude-sonnet-5",
  tokens_used: 500,
};

describe("analyzePricing", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts quote_id to /v1/ai/copilot/analyze-pricing", async () => {
    mockFetchOnce(200, SAMPLE_PRICING_RESULT);
    const result = await analyzePricing("tok", "22222222-2222-2222-2222-222222222222");
    expect(result.margin.recommendation).toBe("Margins look healthy.");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/ai/copilot/analyze-pricing");
    expect(call[1]?.method).toBe("POST");
    expect(JSON.parse(call[1]?.body as string)).toEqual({
      quote_id: "22222222-2222-2222-2222-222222222222",
    });
  });
});

describe("findMissingItems", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts quote_id and optional job_description to /v1/ai/copilot/missing-items", async () => {
    mockFetchOnce(200, {
      quote_id: "22222222-2222-2222-2222-222222222222",
      trade: "electrical",
      completeness_score: 72,
      summary: "Missing a permit line.",
      missing: [],
      model_id: "claude-sonnet-5",
      tokens_used: 400,
    });
    const result = await findMissingItems(
      "tok",
      "22222222-2222-2222-2222-222222222222",
      "Panel upgrade",
    );
    expect(result.completeness_score).toBe(72);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/ai/copilot/missing-items");
    expect(JSON.parse(call[1]?.body as string)).toEqual({
      quote_id: "22222222-2222-2222-2222-222222222222",
      job_description: "Panel upgrade",
    });
  });
});

describe("rewriteTexts", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts texts to /v1/ai/copilot/rewrite with a default professional tone", async () => {
    mockFetchOnce(200, {
      rewritten: ["Replace the panel."],
      model_id: "claude-sonnet-5",
      tokens_used: 80,
    });
    const result = await rewriteTexts("tok", ["replace da panel"]);
    expect(result.rewritten).toEqual(["Replace the panel."]);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(call[1]?.body as string)).toEqual({
      texts: ["replace da panel"],
      tone: "professional",
      context_hint: undefined,
    });
  });
});

describe("addMissingItemToQuote", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts a zero-priced line item mapped from the missing item", async () => {
    mockFetchOnce(201, {
      id: "l9",
      kind: "labor",
      description: "Pull permit",
      quantity: 1,
      unit: "each",
      unit_cost_minor: 0,
      markup_bps: 0,
      unit_price_minor: 0,
      line_total_minor: 0,
      is_optional: false,
      sort_order: 0,
    });
    const item: MissingItem = {
      description: "Pull permit",
      category: "labor",
      item_name: "Permit",
      estimated_quantity: 1,
      unit: "each",
      reasoning: "Required for inspection.",
      priority: "critical",
    };
    await addMissingItemToQuote("tok", "22222222-2222-2222-2222-222222222222", item);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes/22222222-2222-2222-2222-222222222222/line-items");
    expect(JSON.parse(call[1]?.body as string)).toEqual({
      description: "Pull permit",
      kind: "labor",
      quantity: 1,
      unit: "each",
      unit_cost_minor: 0,
      markup_bps: 0,
      unit_price_minor: 0,
    });
  });
});

describe("applyMarkupSuggestion", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("PUTs markup_bps to the line item", async () => {
    mockFetchOnce(200, {
      id: "l1",
      kind: "material",
      description: "Panel",
      quantity: 1,
      unit: "each",
      unit_cost_minor: 10000,
      markup_bps: 4000,
      unit_price_minor: 14000,
      line_total_minor: 14000,
      is_optional: false,
      sort_order: 0,
    });
    await applyMarkupSuggestion("tok", "22222222-2222-2222-2222-222222222222", "l1", 4000);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes/22222222-2222-2222-2222-222222222222/line-items/l1");
    expect(call[1]?.method).toBe("PUT");
    expect(JSON.parse(call[1]?.body as string)).toEqual({ markup_bps: 4000 });
  });
});

describe("updateLineItemDescription", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("PUTs description to the line item", async () => {
    mockFetchOnce(200, {
      id: "l1",
      kind: "material",
      description: "Replace the panel.",
      quantity: 1,
      unit: "each",
      unit_cost_minor: 10000,
      markup_bps: 4000,
      unit_price_minor: 14000,
      line_total_minor: 14000,
      is_optional: false,
      sort_order: 0,
    });
    await updateLineItemDescription(
      "tok",
      "22222222-2222-2222-2222-222222222222",
      "l1",
      "Replace the panel.",
    );
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes/22222222-2222-2222-2222-222222222222/line-items/l1");
    expect(call[1]?.method).toBe("PUT");
    expect(JSON.parse(call[1]?.body as string)).toEqual({ description: "Replace the panel." });
  });
});

describe("missingItemCategoryToItemKind", () => {
  it("passes each category through unchanged", () => {
    expect(missingItemCategoryToItemKind("material")).toBe("material");
    expect(missingItemCategoryToItemKind("labor")).toBe("labor");
    expect(missingItemCategoryToItemKind("equipment")).toBe("equipment");
  });
});

describe("priorityBadgeVariant", () => {
  it("maps each priority to its badge variant", () => {
    expect(priorityBadgeVariant("critical")).toBe("destructive");
    expect(priorityBadgeVariant("recommended")).toBe("warning");
    expect(priorityBadgeVariant("optional")).toBe("secondary");
  });
});

describe("formatBpsPercent", () => {
  it("formats basis points as a one-decimal percent", () => {
    expect(formatBpsPercent(2050)).toBe("20.5%");
    expect(formatBpsPercent(0)).toBe("0.0%");
    expect(formatBpsPercent(10000)).toBe("100.0%");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/web && pnpm vitest run src/lib/copilot.test.ts`
Expected: FAIL — `Cannot find module '@/lib/copilot'` (the file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `apps/web/src/lib/copilot.ts`:

```typescript
import { apiFetch } from "@/lib/api-client";
import { AI_REQUEST_TIMEOUT_MS } from "@/lib/ai";
import type { LineItem } from "@/lib/quotes";

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

export function analyzePricing(token: string, quoteId: string): Promise<PricingAnalysisResult> {
  return apiFetch<PricingAnalysisResult>("/v1/ai/copilot/analyze-pricing", {
    method: "POST",
    token,
    body: { quote_id: quoteId },
    timeoutMs: AI_REQUEST_TIMEOUT_MS,
  });
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

export function findMissingItems(
  token: string,
  quoteId: string,
  jobDescription?: string,
): Promise<MissingItemsResult> {
  return apiFetch<MissingItemsResult>("/v1/ai/copilot/missing-items", {
    method: "POST",
    token,
    body: { quote_id: quoteId, job_description: jobDescription || undefined },
    timeoutMs: AI_REQUEST_TIMEOUT_MS,
  });
}

export interface CopilotRewriteResult {
  rewritten: string[];
  model_id: string;
  tokens_used: number;
}

export function rewriteTexts(
  token: string,
  texts: string[],
  tone = "professional",
  contextHint?: string,
): Promise<CopilotRewriteResult> {
  return apiFetch<CopilotRewriteResult>("/v1/ai/copilot/rewrite", {
    method: "POST",
    token,
    body: { texts, tone, context_hint: contextHint },
    timeoutMs: AI_REQUEST_TIMEOUT_MS,
  });
}

/** The three missing-item category values are already valid quote-service
 * ItemKind values — a direct passthrough, not a lossy mapping. */
export function missingItemCategoryToItemKind(category: MissingItemCategory): LineItem["kind"] {
  return category;
}

export function addMissingItemToQuote(
  token: string,
  quoteId: string,
  item: MissingItem,
): Promise<LineItem> {
  return apiFetch<LineItem>(`/v1/quotes/${quoteId}/line-items`, {
    method: "POST",
    token,
    body: {
      description: item.description,
      kind: missingItemCategoryToItemKind(item.category),
      quantity: item.estimated_quantity,
      unit: item.unit,
      unit_cost_minor: 0,
      markup_bps: 0,
      unit_price_minor: 0,
    },
  });
}

export function applyMarkupSuggestion(
  token: string,
  quoteId: string,
  lineItemId: string,
  markupBps: number,
): Promise<LineItem> {
  return apiFetch<LineItem>(`/v1/quotes/${quoteId}/line-items/${lineItemId}`, {
    method: "PUT",
    token,
    body: { markup_bps: markupBps },
  });
}

export function updateLineItemDescription(
  token: string,
  quoteId: string,
  lineItemId: string,
  description: string,
): Promise<LineItem> {
  return apiFetch<LineItem>(`/v1/quotes/${quoteId}/line-items/${lineItemId}`, {
    method: "PUT",
    token,
    body: { description },
  });
}

/** Badge variant for a missing item's priority — pure, unit-tested. */
export function priorityBadgeVariant(
  priority: MissingItemPriority,
): "destructive" | "warning" | "secondary" {
  switch (priority) {
    case "critical":
      return "destructive";
    case "recommended":
      return "warning";
    case "optional":
      return "secondary";
  }
}

/** Basis points -> a one-decimal percent string, e.g. 2050 -> "20.5%". */
export function formatBpsPercent(bps: number): string {
  return `${(bps / 100).toFixed(1)}%`;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/web && pnpm vitest run src/lib/copilot.test.ts`
Expected: PASS — all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/copilot.ts apps/web/src/lib/copilot.test.ts
git commit -m "feat: add copilot.ts data layer for T202b (pricing, missing-items, rewrite)"
```

---

### Task 3: `CopilotPanel` component

**Files:**

- Create: `apps/web/src/components/ai/copilot-panel.tsx`

**Interfaces:**

- Consumes: everything from Task 2's `@/lib/copilot` (`analyzePricing`, `findMissingItems`, `applyMarkupSuggestion`, `addMissingItemToQuote`, `formatBpsPercent`, `priorityBadgeVariant`, `MissingItem`, `MissingItemsResult`, `PricingAnalysisResult` types); `describeAiSubmitError` from `@/lib/ai`; `formatMoney` from `@/lib/money`; `Quote` type from `@/lib/quotes`; `Card`/`CardHeader`/`CardTitle`/`CardContent` from `@/components/ui/card`; `Badge` from `@/components/ui/badge`; `Button` from `@/components/ui/button`.
- Produces (consumed by Task 4): `export function CopilotPanel({ token, quote }: { token: string; quote: Quote }): JSX.Element`.

There is no unit test for this file — per the Global Constraints, this codebase verifies UI components live in the browser, not via `.test.tsx` files. This task's "test cycle" is the typecheck in Step 2 and the live verification in Task 5.

- [ ] **Step 1: Write the component**

Create `apps/web/src/components/ai/copilot-panel.tsx`:

```tsx
"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { describeAiSubmitError } from "@/lib/ai";
import {
  addMissingItemToQuote,
  analyzePricing,
  applyMarkupSuggestion,
  findMissingItems,
  formatBpsPercent,
  priorityBadgeVariant,
  type MissingItem,
  type MissingItemsResult,
  type PricingAnalysisResult,
} from "@/lib/copilot";
import { formatMoney } from "@/lib/money";
import type { Quote } from "@/lib/quotes";

interface CopilotPanelProps {
  token: string;
  quote: Quote;
}

/**
 * On-demand AI Copilot actions for a saved quote (T202b). Nothing here runs
 * automatically — every analysis is a metered LLM call against the tenant's
 * daily spend cap, so each section is gated behind its own button.
 */
export function CopilotPanel({ token, quote }: CopilotPanelProps) {
  const queryClient = useQueryClient();

  function invalidateQuote() {
    queryClient.invalidateQueries({ queryKey: ["quotes", quote.id] });
  }

  const [pricingError, setPricingError] = React.useState<string | null>(null);
  const [pricing, setPricing] = React.useState<PricingAnalysisResult | null>(null);

  const analyzeMutation = useMutation({
    mutationFn: () => analyzePricing(token, quote.id),
    onSuccess: (result) => {
      setPricing(result);
      setPricingError(null);
    },
    onError: (err) => setPricingError(describeAiSubmitError(err)),
  });

  const applyMutation = useMutation({
    mutationFn: (vars: { lineItemId: string; markupBps: number }) =>
      applyMarkupSuggestion(token, quote.id, vars.lineItemId, vars.markupBps),
    onSuccess: invalidateQuote,
    onError: (err) => setPricingError(describeAiSubmitError(err)),
  });

  const [jobDescription, setJobDescription] = React.useState("");
  const [missingError, setMissingError] = React.useState<string | null>(null);
  const [missingResult, setMissingResult] = React.useState<MissingItemsResult | null>(null);

  const findMissingMutation = useMutation({
    mutationFn: () => findMissingItems(token, quote.id, jobDescription || undefined),
    onSuccess: (result) => {
      setMissingResult(result);
      setMissingError(null);
    },
    onError: (err) => setMissingError(describeAiSubmitError(err)),
  });

  const addMissingMutation = useMutation({
    mutationFn: (item: MissingItem) => addMissingItemToQuote(token, quote.id, item),
    onSuccess: invalidateQuote,
    onError: (err) => setMissingError(describeAiSubmitError(err)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI Copilot</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Pricing analysis</h3>
            <Button
              type="button"
              size="sm"
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending || quote.line_items.length === 0}
            >
              {analyzeMutation.isPending ? "Analyzing…" : "Analyze Pricing"}
            </Button>
          </div>
          {pricingError && <p className="text-sm text-destructive">{pricingError}</p>}
          {pricing && (
            <div className="space-y-3 rounded-md border border-dashed border-input p-3">
              <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <div>
                  <p className="text-muted-foreground">Cost</p>
                  <p className="font-medium">
                    {formatMoney(pricing.margin.total_cost_minor, quote.currency)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Revenue</p>
                  <p className="font-medium">
                    {formatMoney(pricing.margin.total_revenue_minor, quote.currency)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Gross margin</p>
                  <p className="font-medium">{formatBpsPercent(pricing.margin.gross_margin_bps)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Avg. markup</p>
                  <p className="font-medium">
                    {formatBpsPercent(pricing.margin.average_markup_bps)}
                  </p>
                </div>
              </div>
              <p className="text-sm">{pricing.margin.recommendation}</p>

              {pricing.suggestions.length > 0 && (
                <ul className="space-y-2">
                  {pricing.suggestions.map((suggestion) => {
                    const lineItem = quote.line_items.find(
                      (item) => item.id === suggestion.line_item_id,
                    );
                    const isLowMargin = pricing.margin.low_margin_item_ids.includes(
                      suggestion.line_item_id,
                    );
                    return (
                      <li key={suggestion.line_item_id} className="rounded-md border p-2 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">
                            {lineItem?.description ?? suggestion.line_item_id}
                          </span>
                          {isLowMargin && <Badge variant="destructive">Low margin</Badge>}
                        </div>
                        <p className="text-muted-foreground">
                          Current markup {formatBpsPercent(suggestion.current_markup_bps)}
                          {suggestion.suggested_markup_bps !== null && (
                            <> → suggested {formatBpsPercent(suggestion.suggested_markup_bps)}</>
                          )}
                        </p>
                        <p className="text-muted-foreground">{suggestion.reasoning}</p>
                        {suggestion.suggested_markup_bps !== null && (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="mt-2"
                            onClick={() =>
                              applyMutation.mutate({
                                lineItemId: suggestion.line_item_id,
                                markupBps: suggestion.suggested_markup_bps as number,
                              })
                            }
                            disabled={applyMutation.isPending}
                          >
                            Apply suggested markup
                          </Button>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="space-y-3 border-t pt-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Missing items</h3>
            <Button
              type="button"
              size="sm"
              onClick={() => findMissingMutation.mutate()}
              disabled={findMissingMutation.isPending}
            >
              {findMissingMutation.isPending ? "Checking…" : "Find Missing Items"}
            </Button>
          </div>
          <textarea
            className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="Optional: describe the job for better results"
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
          />
          {missingError && <p className="text-sm text-destructive">{missingError}</p>}
          {missingResult && (
            <div className="space-y-3 rounded-md border border-dashed border-input p-3">
              <p className="text-sm font-medium">
                Completeness: {missingResult.completeness_score}/100
              </p>
              <p className="text-sm text-muted-foreground">{missingResult.summary}</p>
              {missingResult.missing.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing missing found.</p>
              ) : (
                <ul className="space-y-2">
                  {missingResult.missing.map((item, index) => (
                    <li
                      key={`${item.item_name}-${index}`}
                      className="rounded-md border p-2 text-sm"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{item.description}</span>
                        <Badge variant={priorityBadgeVariant(item.priority)} className="capitalize">
                          {item.priority}
                        </Badge>
                      </div>
                      <p className="text-muted-foreground">
                        {item.estimated_quantity} {item.unit} — {item.reasoning}
                      </p>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="mt-2"
                        onClick={() => addMissingMutation.mutate(item)}
                        disabled={addMissingMutation.isPending}
                      >
                        Add to Quote
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Run typecheck to verify it compiles**

Run: `cd apps/web && pnpm typecheck`
Expected: PASS — no type errors (the component isn't wired into any page yet, so this only checks the file compiles standalone plus the rest of the existing app).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/ai/copilot-panel.tsx
git commit -m "feat: add CopilotPanel component (pricing analysis + missing items)"
```

---

### Task 4: `InlineRewriteEditor` + wire everything into the quote detail page

**Files:**

- Create: `apps/web/src/components/ai/inline-rewrite-editor.tsx`
- Modify: `apps/web/src/app/(app)/quotes/[id]/page.tsx` (full-file replacement, per the codebase's established pattern for this file — see T201b Task 5)

**Interfaces:**

- Consumes: `rewriteTexts`, `updateLineItemDescription` from `@/lib/copilot` (Task 2); `describeAiSubmitError` from `@/lib/ai`; `CopilotPanel` from `@/components/ai/copilot-panel` (Task 3).
- Produces: `export function InlineRewriteEditor({ token, quoteId, lineItemId, initialText, onSaved, onCancel }): JSX.Element` — a self-contained row-level editor, not consumed outside this page.

- [ ] **Step 1: Write the inline rewrite editor**

Create `apps/web/src/components/ai/inline-rewrite-editor.tsx`:

```tsx
"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { describeAiSubmitError } from "@/lib/ai";
import { rewriteTexts, updateLineItemDescription } from "@/lib/copilot";

interface InlineRewriteEditorProps {
  token: string;
  quoteId: string;
  lineItemId: string;
  initialText: string;
  onSaved: () => void;
  onCancel: () => void;
}

/**
 * Replaces a line item's description cell while active. "Rewrite" calls the
 * copilot (advisory only — text stays in this textarea for editing); "Save"
 * is the only action that writes to quote-service, so nothing is ever
 * auto-applied (M16 web UI spec §5).
 */
export function InlineRewriteEditor({
  token,
  quoteId,
  lineItemId,
  initialText,
  onSaved,
  onCancel,
}: InlineRewriteEditorProps) {
  const [text, setText] = React.useState(initialText);
  const [error, setError] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const rewriteMutation = useMutation({
    mutationFn: () => rewriteTexts(token, [text]),
    onSuccess: (result) => {
      setText(result.rewritten[0]);
      setError(null);
    },
    onError: (err) => setError(describeAiSubmitError(err)),
  });

  const saveMutation = useMutation({
    mutationFn: () => updateLineItemDescription(token, quoteId, lineItemId, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotes", quoteId] });
      onSaved();
    },
    onError: (err) => setError(describeAiSubmitError(err)),
  });

  const isBusy = rewriteMutation.isPending || saveMutation.isPending;

  return (
    <div className="space-y-2">
      <textarea
        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => rewriteMutation.mutate()}
          disabled={isBusy || text.trim().length === 0}
        >
          {rewriteMutation.isPending ? "Rewriting…" : "Rewrite"}
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={isBusy || text.trim().length === 0}
        >
          {saveMutation.isPending ? "Saving…" : "Save"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={isBusy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Replace the quote detail page**

Replace the full contents of `apps/web/src/app/(app)/quotes/[id]/page.tsx` with:

```tsx
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { acceptQuote, getQuote, rejectQuote, sendQuote, statusBadgeVariant } from "@/lib/quotes";
import { formatMoney } from "@/lib/money";
import { ApiError } from "@/lib/api-client";
import { isUnmatchedTask, type QuoteDraft } from "@/lib/ai";
import { AiDraftBanner } from "@/components/ai/ai-draft-banner";
import { CopilotPanel } from "@/components/ai/copilot-panel";
import { InlineRewriteEditor } from "@/components/ai/inline-rewrite-editor";

const AI_DRAFT_STORAGE_PREFIX = "ai-draft:";

export default function QuoteDetailPage() {
  const token = useAuthGuard();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [aiDraft, setAiDraft] = React.useState<QuoteDraft | null>(null);
  const [rewritingLineItemId, setRewritingLineItemId] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (searchParams.get("from") !== "ai") return;
    const key = `${AI_DRAFT_STORAGE_PREFIX}${params.id}`;
    const raw = sessionStorage.getItem(key);
    if (!raw) return;
    sessionStorage.removeItem(key);
    try {
      setAiDraft(JSON.parse(raw) as QuoteDraft);
    } catch {
      // Malformed/stale sessionStorage entry — ignore; the plain quote page still renders fine.
    }
  }, [params.id, searchParams]);

  const {
    data: quote,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["quotes", params.id],
    queryFn: () => getQuote(token as string, params.id),
    enabled: !!token,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["quotes", params.id] });
    queryClient.invalidateQueries({ queryKey: ["quotes"] });
  }

  const sendMutation = useMutation({
    mutationFn: () => sendQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to send."),
  });
  const acceptMutation = useMutation({
    mutationFn: () => acceptQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to accept."),
  });
  const rejectMutation = useMutation({
    mutationFn: () => rejectQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to reject."),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading quote…</p>;
  if (isError || !quote) return <p className="text-sm text-destructive">Quote not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{quote.number}</h1>
            <Badge variant={statusBadgeVariant(quote.status)} className="capitalize">
              {quote.status}
            </Badge>
          </div>
          <p className="text-muted-foreground">{quote.title ?? "Untitled quote"}</p>
        </div>
        <div className="flex gap-2">
          {(quote.status === "draft" ||
            quote.status === "sent" ||
            quote.status === "viewed" ||
            quote.status === "accepted") && (
            <Link
              href={`/proposals/new?quote_id=${quote.id}`}
              className={buttonVariants({ variant: "outline" })}
            >
              Create Proposal
            </Link>
          )}
          {quote.status === "draft" && (
            <Button onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
              {sendMutation.isPending ? "Sending…" : "Send"}
            </Button>
          )}
          {(quote.status === "sent" || quote.status === "viewed") && (
            <>
              <Button
                variant="outline"
                onClick={() => rejectMutation.mutate()}
                disabled={rejectMutation.isPending}
              >
                Mark Rejected
              </Button>
              <Button onClick={() => acceptMutation.mutate()} disabled={acceptMutation.isPending}>
                Mark Accepted
              </Button>
            </>
          )}
        </div>
      </div>

      {aiDraft && <AiDraftBanner draft={aiDraft} />}

      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Line Items</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Description</th>
                  <th className="py-2 pr-4 text-right font-medium">Qty</th>
                  <th className="py-2 pr-4 font-medium">Unit</th>
                  <th className="py-2 pr-4 text-right font-medium">Unit Price</th>
                  <th className="py-2 pr-4 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {quote.line_items.map((item, index) => {
                  const task = aiDraft?.tasks[index];
                  const flagUnmatched = task ? isUnmatchedTask(task) : false;
                  return (
                    <tr key={item.id} className="border-b last:border-0">
                      <td className="py-3 pr-4">
                        {rewritingLineItemId === item.id ? (
                          <InlineRewriteEditor
                            token={token as string}
                            quoteId={quote.id}
                            lineItemId={item.id}
                            initialText={item.description}
                            onSaved={() => setRewritingLineItemId(null)}
                            onCancel={() => setRewritingLineItemId(null)}
                          />
                        ) : (
                          <div className="flex items-center gap-2">
                            {item.description}
                            {flagUnmatched && (
                              <Badge variant="destructive" className="whitespace-nowrap">
                                Unmatched — needs pricing
                              </Badge>
                            )}
                            <button
                              type="button"
                              aria-label="Rewrite description"
                              className="text-muted-foreground hover:text-foreground"
                              onClick={() => setRewritingLineItemId(item.id)}
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-right">{item.quantity}</td>
                      <td className="py-3 pr-4">{item.unit}</td>
                      <td className="py-3 pr-4 text-right">
                        {formatMoney(item.unit_price_minor, quote.currency)}
                      </td>
                      <td className="py-3 pr-4 text-right font-medium">
                        {formatMoney(item.line_total_minor, quote.currency)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex justify-end">
            <div className="w-56 space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>{formatMoney(quote.subtotal_minor, quote.currency)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tax</span>
                <span>{formatMoney(quote.tax_minor, quote.currency)}</span>
              </div>
              <div className="flex justify-between border-t pt-1 text-base font-semibold">
                <span>Total</span>
                <span>{formatMoney(quote.total_minor, quote.currency)}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <CopilotPanel token={token as string} quote={quote} />
    </div>
  );
}
```

- [ ] **Step 3: Run typecheck and the full web test suite**

Run: `cd apps/web && pnpm typecheck && pnpm vitest run`
Expected: PASS — no type errors; all existing tests plus Task 1's and Task 2's new tests pass (94 total: 84 pre-existing + 1 from Task 1 + 9 from Task 2).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/ai/inline-rewrite-editor.tsx "apps/web/src/app/(app)/quotes/[id]/page.tsx"
git commit -m "feat: wire CopilotPanel and inline rewrite into the quote detail page"
```

---

### Task 5: Gates, live verification, tracker update

**Files:**

- Modify: `TASKS.md` (T202b row)
- Modify: `tracking/PROGRESS-TRACKER.csv` (T202b row)

**Interfaces:**

- Consumes: nothing new — this task only verifies and documents Tasks 1-4's output.

- [ ] **Step 1: Run the full gate suite**

Run each of these from the repo root and confirm the listed result:

```bash
cd apps/web && pnpm vitest run
```

Expected: all test files pass (94 tests: 84 pre-T202b + 1 new in `ai.test.ts` + 9 new in `copilot.test.ts`).

```bash
cd apps/web && pnpm typecheck
```

Expected: no output (clean).

```bash
cd apps/web && pnpm build
```

Expected: `✓ Compiled successfully`, all routes generated including `/quotes/[id]`.

- [ ] **Step 2: Live-verify in the browser**

Start the web app's dev server and the API gateway/backends per this repo's existing dev-run instructions. Navigate to an existing quote's detail page (`/quotes/{id}`) and confirm:

1. The "AI Copilot" card renders below Line Items.
2. Clicking "Analyze Pricing" on a quote with line items shows the margin block and per-line suggestions; clicking "Apply suggested markup" on a suggestion updates that line's markup/price in the Line Items table above (query invalidation working).
3. Clicking "Find Missing Items" (with or without a job description) shows a completeness score and a list of missing items; clicking "Add to Quote" on one adds a new $0 line item to the table above.
4. Clicking the pencil icon next to a line item's description opens the inline editor; "Rewrite" replaces the textarea text with the AI's rewritten version; "Save" persists it and closes the editor, reflecting the new description in the table; "Cancel" discards without saving.
5. Trigger at least one error path (e.g. temporarily stop the ai-service, or exceed the daily spend cap if feasible) and confirm `describeAiSubmitError`'s message renders instead of a raw status code.

- [ ] **Step 3: Update `TASKS.md`**

Find the `T202b` row (currently `- [ ] \`T202b\` **[A2]** M16 AI Copilot web UI: ...`) and mark it done, following this repository's existing convention for a completed row (see the `T201`/`T202`/`T201`-adjacent rows for the exact style: `[x]`, a `✅ **DONE (<date>)**`marker, a one-paragraph summary of what shipped, test counts, and a link to the plan doc). Use today's date and reference`docs/modules/M16-ai-copilot-web-ui-plan.md` and this spec's path.

- [ ] **Step 4: Update `tracking/PROGRESS-TRACKER.csv`**

Update the `T202b` row's status from `NOT_STARTED` to `DONE` (matching the column format of the `T203`/`T201b` rows already in the file).

- [ ] **Step 5: Commit**

```bash
git add TASKS.md tracking/PROGRESS-TRACKER.csv
git commit -m "docs: mark T202b done in TASKS.md and PROGRESS-TRACKER.csv"
```
