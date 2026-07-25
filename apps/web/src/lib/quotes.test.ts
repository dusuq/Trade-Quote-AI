import { afterEach, describe, expect, it, vi } from "vitest";
import {
  calculateFormSubtotalMinor,
  listQuotes,
  newQuoteFormSchema,
  statusBadgeVariant,
  toQuoteCreatePayload,
  type NewQuoteFormInput,
} from "@/lib/quotes";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";

function baseForm(overrides: Partial<NewQuoteFormInput> = {}): NewQuoteFormInput {
  return {
    customerId: CUSTOMER_ID,
    title: "Panel upgrade",
    taxRatePercent: 8.75,
    lineItems: [
      { description: "200A panel", quantity: 1, unit: "each", unitPriceDollars: 850 },
      { description: "LED can light", quantity: 12, unit: "each", unitPriceDollars: 45 },
    ],
    ...overrides,
  };
}

describe("newQuoteFormSchema", () => {
  it("accepts a valid form", () => {
    expect(newQuoteFormSchema.safeParse(baseForm()).success).toBe(true);
  });

  it("rejects a non-UUID customerId", () => {
    expect(newQuoteFormSchema.safeParse(baseForm({ customerId: "not-a-uuid" })).success).toBe(
      false,
    );
  });

  it("rejects an empty line-items array", () => {
    expect(newQuoteFormSchema.safeParse(baseForm({ lineItems: [] })).success).toBe(false);
  });

  it("rejects a line item with zero quantity", () => {
    const form = baseForm({
      lineItems: [{ description: "x", quantity: 0, unit: "each", unitPriceDollars: 10 }],
    });
    expect(newQuoteFormSchema.safeParse(form).success).toBe(false);
  });

  it("rejects a line item with an empty description", () => {
    const form = baseForm({
      lineItems: [{ description: "", quantity: 1, unit: "each", unitPriceDollars: 10 }],
    });
    expect(newQuoteFormSchema.safeParse(form).success).toBe(false);
  });
});

describe("toQuoteCreatePayload", () => {
  it("converts dollars to integer minor units and percent to basis points", () => {
    const payload = toQuoteCreatePayload(baseForm());
    expect(payload.customer_id).toBe(CUSTOMER_ID);
    expect(payload.tax_rate_bps).toBe(875);
    expect(payload.initial_line_items).toHaveLength(2);
    expect(payload.initial_line_items[0]).toMatchObject({
      description: "200A panel",
      quantity: 1,
      unit_price_minor: 85000,
      sort_order: 0,
    });
    expect(payload.initial_line_items[1]).toMatchObject({
      unit_price_minor: 4500,
      sort_order: 1,
    });
  });

  it("sends null title when omitted", () => {
    const payload = toQuoteCreatePayload(baseForm({ title: "" }));
    expect(payload.title).toBeNull();
  });

  it("never emits a float for unit_price_minor", () => {
    const payload = toQuoteCreatePayload(
      baseForm({
        lineItems: [{ description: "x", quantity: 1, unit: "each", unitPriceDollars: 19.999 }],
      }),
    );
    expect(Number.isInteger(payload.initial_line_items[0].unit_price_minor)).toBe(true);
  });
});

describe("calculateFormSubtotalMinor", () => {
  it("sums quantity * unit price across line items", () => {
    const subtotal = calculateFormSubtotalMinor(baseForm().lineItems);
    // 1 * $850.00 + 12 * $45.00 = $850 + $540 = $1,390.00 = 139000 cents
    expect(subtotal).toBe(139000);
  });

  it("returns 0 for an empty list", () => {
    expect(calculateFormSubtotalMinor([])).toBe(0);
  });

  it("treats a blank price as 0", () => {
    const subtotal = calculateFormSubtotalMinor([
      { description: "x", quantity: 2, unit: "each", unitPriceDollars: Number.NaN },
    ]);
    expect(subtotal).toBe(0);
  });
});

describe("statusBadgeVariant", () => {
  it("maps accepted to success", () => {
    expect(statusBadgeVariant("accepted")).toBe("success");
  });
  it("maps draft to warning", () => {
    expect(statusBadgeVariant("draft")).toBe("warning");
  });
  it("maps rejected and expired to destructive", () => {
    expect(statusBadgeVariant("rejected")).toBe("destructive");
    expect(statusBadgeVariant("expired")).toBe("destructive");
  });
  it("maps sent and viewed to default", () => {
    expect(statusBadgeVariant("sent")).toBe("default");
    expect(statusBadgeVariant("viewed")).toBe("default");
  });
});

describe("listQuotes", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("appends a limit query param when provided", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => JSON.stringify([]) }),
    );
    await listQuotes("tok", 5);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes?limit=5");
  });

  it("omits the query string when limit is not provided", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => JSON.stringify([]) }),
    );
    await listQuotes("tok");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes");
    expect(call[0]).not.toContain("?");
  });
});
