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
