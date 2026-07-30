// apps/web/src/lib/ai.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import {
  describeAiSubmitError,
  generateScopeText,
  isUnmatchedTask,
  lineItemKindToTaskCategory,
  quoteLineItemsToScopeTasks,
  submitTextToQuote,
  submitVoiceToQuote,
  type ExtractedTask,
} from "@/lib/ai";
import type { Quote } from "@/lib/quotes";

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

const SAMPLE_DRAFT = {
  quote_id: "22222222-2222-2222-2222-222222222222",
  trade: "electrical",
  summary: "Panel upgrade and lighting",
  notes: "",
  tasks: [],
  unmatched_count: 0,
  model_id: "claude-opus-5",
  tokens_used: 1200,
  input_kind: "text",
  transcript: null,
  language: null,
};

describe("submitTextToQuote", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to /v1/ai/text-to-quote", async () => {
    mockFetchOnce(201, SAMPLE_DRAFT);
    const result = await submitTextToQuote("tok", {
      text: "Replace the panel with a 200 amp.",
      customer_id: "11111111-1111-1111-1111-111111111111",
    });
    expect(result.quote_id).toBe(SAMPLE_DRAFT.quote_id);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/ai/text-to-quote");
    expect(call[1]?.method).toBe("POST");
  });
});

describe("submitVoiceToQuote", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts multipart form data to /v1/ai/voice-to-quote", async () => {
    mockFetchOnce(201, { ...SAMPLE_DRAFT, input_kind: "voice" });
    const audioBlob = new Blob(["fake-audio"], { type: "audio/webm" });
    await submitVoiceToQuote("tok", {
      audioBlob,
      customer_id: "11111111-1111-1111-1111-111111111111",
    });
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/ai/voice-to-quote");
    expect(call[1]?.body).toBeInstanceOf(FormData);
    const form = call[1]?.body as FormData;
    expect(form.get("customer_id")).toBe("11111111-1111-1111-1111-111111111111");
    expect(form.get("audio")).toBeInstanceOf(Blob);
  });
});

describe("generateScopeText", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to /v1/ai/scope-writer", async () => {
    mockFetchOnce(200, { scope_text: "We will...", model_id: "claude-sonnet-5", tokens_used: 300 });
    const result = await generateScopeText("tok", {
      trade: "electrical",
      summary: "Panel upgrade",
      tasks: [{ description: "Panel", category: "material", item_name: "Panel", quantity: 1, unit: "each" }],
      tone: "professional",
    });
    expect(result.scope_text).toBe("We will...");
  });
});

describe("lineItemKindToTaskCategory", () => {
  it("maps labor and equipment directly", () => {
    expect(lineItemKindToTaskCategory("labor")).toBe("labor");
    expect(lineItemKindToTaskCategory("equipment")).toBe("equipment");
  });

  it("falls back to material for consumable/rental/package", () => {
    expect(lineItemKindToTaskCategory("consumable")).toBe("material");
    expect(lineItemKindToTaskCategory("rental")).toBe("material");
    expect(lineItemKindToTaskCategory("package")).toBe("material");
    expect(lineItemKindToTaskCategory("material")).toBe("material");
  });
});

describe("quoteLineItemsToScopeTasks", () => {
  it("maps a quote's line items into ScopeTaskInput shape", () => {
    const quote = {
      line_items: [
        {
          id: "l1",
          kind: "labor",
          description: "Install panel",
          quantity: 2,
          unit: "hour",
          unit_cost_minor: 0,
          markup_bps: 0,
          unit_price_minor: 0,
          line_total_minor: 0,
          is_optional: false,
          sort_order: 0,
        },
      ],
    } as Quote;
    const tasks = quoteLineItemsToScopeTasks(quote);
    expect(tasks).toEqual([
      { description: "Install panel", category: "labor", item_name: "Install panel", quantity: 2, unit: "hour" },
    ]);
  });
});

describe("describeAiSubmitError", () => {
  it("maps known statuses to specific messages", () => {
    expect(describeAiSubmitError(new ApiError(413, "x"))).toContain("too long");
    expect(describeAiSubmitError(new ApiError(400, "x"))).toContain("format");
    expect(describeAiSubmitError(new ApiError(429, "x"))).toContain("usage limit");
    expect(describeAiSubmitError(new ApiError(502, "x"))).toContain("temporarily unavailable");
    expect(describeAiSubmitError(new ApiError(422, "x"))).toContain("more detail");
  });

  it("maps 503 to a copilot-disabled message", () => {
    expect(describeAiSubmitError(new ApiError(503, "x"))).toBe(
      "AI Copilot is currently disabled.",
    );
  });

  it("falls back to the error message for an unmapped status", () => {
    expect(describeAiSubmitError(new ApiError(500, "boom"))).toBe("boom");
  });

  it("falls back to a generic message for a non-ApiError", () => {
    expect(describeAiSubmitError(new Error("network down"))).toBe(
      "Something went wrong. Please try again.",
    );
  });
});

describe("isUnmatchedTask", () => {
  it("is true when pricebook_item_id is null", () => {
    const task = { pricebook_item_id: null } as ExtractedTask;
    expect(isUnmatchedTask(task)).toBe(true);
  });

  it("is false when pricebook_item_id is set", () => {
    const task = { pricebook_item_id: "pb-1" } as ExtractedTask;
    expect(isUnmatchedTask(task)).toBe(false);
  });
});
