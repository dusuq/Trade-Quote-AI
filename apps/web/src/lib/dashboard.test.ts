import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchQuoteSummary,
  formatConversion,
  pickPrimaryTotal,
  resolveBrowserTimezone,
  type CurrencyTotal,
} from "@/lib/dashboard";

describe("formatConversion", () => {
  it("renders an em dash when nothing has been decided", () => {
    expect(formatConversion(0, 0)).toBe("—");
  });

  it("renders a percentage with one decimal when decisions exist", () => {
    expect(formatConversion(4306, 72)).toBe("43.1%");
  });

  it("renders 0.0% when decisions exist but none were accepted", () => {
    expect(formatConversion(0, 5)).toBe("0.0%");
  });

  it("renders 100.0% when every decided quote was accepted", () => {
    expect(formatConversion(10000, 3)).toBe("100.0%");
  });
});

describe("pickPrimaryTotal", () => {
  it("returns null for an empty totals array", () => {
    expect(pickPrimaryTotal([])).toBeNull();
  });

  it("returns the first entry for a single-currency tenant", () => {
    const totals: CurrencyTotal[] = [{ currency: "USD", accepted_value_minor: 4820000 }];
    expect(pickPrimaryTotal(totals)).toEqual(totals[0]);
  });

  it("returns the first entry among multiple currencies, never summed", () => {
    const totals: CurrencyTotal[] = [
      { currency: "USD", accepted_value_minor: 100 },
      { currency: "CAD", accepted_value_minor: 200 },
    ];
    expect(pickPrimaryTotal(totals)).toEqual(totals[0]);
  });
});

describe("resolveBrowserTimezone", () => {
  it("returns a non-empty IANA zone name", () => {
    expect(resolveBrowserTimezone().length).toBeGreaterThan(0);
  });
});

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

describe("fetchQuoteSummary", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests the summary endpoint with tz and range query params", async () => {
    mockFetchOnce(200, {
      timezone: "Australia/Sydney",
      range: "mtd",
      range_start: "2026-07-01T00:00:00+10:00",
      range_end: "2026-07-26T00:00:00+10:00",
      quotes_today: 4,
      pending_count: 12,
      accepted_count: 31,
      decided_count: 72,
      conversion_bps: 4306,
      totals: [],
    });

    await fetchQuoteSummary("tok", "Australia/Sydney", "mtd");

    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes/summary?tz=Australia%2FSydney&range=mtd");
  });

  it("defaults range to mtd when omitted", async () => {
    mockFetchOnce(200, {
      timezone: "UTC",
      range: "mtd",
      range_start: "2026-07-01T00:00:00Z",
      range_end: "2026-07-26T00:00:00Z",
      quotes_today: 0,
      pending_count: 0,
      accepted_count: 0,
      decided_count: 0,
      conversion_bps: 0,
      totals: [],
    });

    await fetchQuoteSummary("tok", "UTC");

    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("range=mtd");
  });

  it("propagates an ApiError when the tz is rejected by the server", async () => {
    mockFetchOnce(400, { message: "unknown timezone: Not/AZone" });
    await expect(fetchQuoteSummary("tok", "Not/AZone")).rejects.toMatchObject({ status: 400 });
  });
});
