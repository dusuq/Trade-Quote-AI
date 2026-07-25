import { describe, expect, it } from "vitest";
import {
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
