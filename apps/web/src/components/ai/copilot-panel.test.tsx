// @vitest-environment jsdom
/**
 * Component tests for the copilot panel's write actions (T202c).
 *
 * The defect these exist for: "Add to Quote" is a POST, so a second click
 * creates a second $0 line item. The old code re-enabled the button on success
 * and left the suggestion in the list, and the added line renders *above* this
 * panel — so a contractor who doesn't scroll gets no confirmation and clicks
 * again. Asserting on the call count is the only way to pin that.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CopilotPanel, missingItemKey } from "@/components/ai/copilot-panel";
import type { MissingItemsResult } from "@/lib/copilot";
import type { Quote } from "@/lib/quotes";

const { addMissingItemToQuote, applyMarkupSuggestion, findMissingItems, analyzePricing } =
  vi.hoisted(() => ({
    addMissingItemToQuote: vi.fn(),
    applyMarkupSuggestion: vi.fn(),
    findMissingItems: vi.fn(),
    analyzePricing: vi.fn(),
  }));

vi.mock("@/lib/copilot", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/copilot")>();
  return { ...actual, addMissingItemToQuote, applyMarkupSuggestion, findMissingItems, analyzePricing };
});

const QUOTE: Quote = {
  id: "quote-1",
  customer_id: "cust-1",
  property_id: null,
  number: "Q-001",
  title: "Panel upgrade",
  status: "draft",
  currency: "USD",
  tax_rate_bps: 0,
  subtotal_minor: 0,
  tax_minor: 0,
  total_minor: 0,
  current_version: 1,
  valid_until: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  line_items: [
    {
      id: "li-1",
      kind: "material",
      description: "200A panel",
      quantity: 1,
      unit: "ea",
      unit_cost_minor: 10_000,
      markup_bps: 2000,
      unit_price_minor: 12_000,
      line_total_minor: 12_000,
      is_optional: false,
      sort_order: 1,
    },
  ],
};

const MISSING: MissingItemsResult = {
  quote_id: "quote-1",
  trade: "electrical",
  completeness_score: 60,
  summary: "Two items look missing.",
  missing: [
    {
      description: "Permit fee",
      category: "material",
      item_name: "permit",
      estimated_quantity: 1,
      unit: "ea",
      reasoning: "Required by the AHJ.",
      priority: "critical",
    },
    {
      description: "Conduit run",
      category: "material",
      item_name: "conduit",
      estimated_quantity: 20,
      unit: "ft",
      reasoning: "Panel is 20ft from the meter.",
      priority: "recommended",
    },
  ],
  model_id: "claude-sonnet-5",
  tokens_used: 100,
};

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CopilotPanel token="jwt" quote={QUOTE} />
    </QueryClientProvider>,
  );
}

/** Runs "Find Missing Items" so the suggestion rows exist. */
async function showMissingItems() {
  findMissingItems.mockResolvedValue(MISSING);
  renderPanel();
  fireEvent.click(screen.getByRole("button", { name: /find missing items/i }));
  await screen.findByText("Permit fee");
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("missingItemKey", () => {
  it("includes the index so duplicate names stay distinct", () => {
    // The model can legitimately return two items with the same name; keying
    // on the name alone would mark both added when one is.
    expect(missingItemKey({ item_name: "conduit" }, 0)).not.toBe(
      missingItemKey({ item_name: "conduit" }, 1),
    );
  });
});

describe("Add to Quote", () => {
  it("cannot be clicked twice — the second click would create a duplicate line", async () => {
    addMissingItemToQuote.mockResolvedValue({ id: "li-2" });
    await showMissingItems();

    const button = screen.getAllByRole("button", { name: /add to quote/i })[0];
    fireEvent.click(button);

    const added = await screen.findByRole("button", { name: /added to quote/i });
    expect((added as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(added);
    await waitFor(() => expect(addMissingItemToQuote).toHaveBeenCalledTimes(1));
  });

  it("adding one item leaves the other row's button usable", async () => {
    addMissingItemToQuote.mockResolvedValue({ id: "li-2" });
    await showMissingItems();

    fireEvent.click(screen.getAllByRole("button", { name: /add to quote/i })[0]);
    await screen.findByRole("button", { name: /added to quote/i });

    const stillAddable = screen.getAllByRole("button", { name: /^add to quote$/i });
    expect(stillAddable).toHaveLength(1);
    expect((stillAddable[0] as HTMLButtonElement).disabled).toBe(false);
  });

  it("reports a failure on the row that failed, and leaves it retryable", async () => {
    addMissingItemToQuote.mockRejectedValue(new Error("boom"));
    await showMissingItems();

    const button = screen.getAllByRole("button", { name: /add to quote/i })[0];
    fireEvent.click(button);

    await screen.findByText(/something went wrong/i);
    // Not marked added — a failed add must stay clickable.
    expect(screen.getAllByRole("button", { name: /^add to quote$/i })).toHaveLength(2);
  });
});

describe("Apply suggested markup", () => {
  it("is idempotent, so it stays enabled after success", async () => {
    // Contrast with Add to Quote: this is a PUT with a fixed value, so
    // re-applying is harmless and the button should not lock out.
    analyzePricing.mockResolvedValue({
      quote_id: "quote-1",
      suggestions: [
        {
          line_item_id: "li-1",
          current_unit_cost_minor: 10_000,
          current_markup_bps: 2000,
          current_unit_price_minor: 12_000,
          suggested_markup_bps: 3000,
          pricebook_unit_cost_minor: null,
          reasoning: "Below trade average.",
        },
      ],
      margin: {
        total_cost_minor: 10_000,
        total_revenue_minor: 12_000,
        gross_margin_bps: 1667,
        average_markup_bps: 2000,
        low_margin_item_ids: [],
        recommendation: "Raise it.",
      },
      model_id: "claude-sonnet-5",
      tokens_used: 50,
    });
    applyMarkupSuggestion.mockResolvedValue({ id: "li-1" });
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /analyze pricing/i }));
    const apply = await screen.findByRole("button", { name: /apply suggested markup/i });

    fireEvent.click(apply);
    await waitFor(() => expect(applyMarkupSuggestion).toHaveBeenCalledTimes(1));
    await waitFor(() => expect((apply as HTMLButtonElement).disabled).toBe(false));
  });
});

describe("labels", () => {
  it("the job description textarea is reachable by its label", () => {
    renderPanel();
    expect(screen.getByLabelText(/job description/i)).toBeDefined();
  });
});
