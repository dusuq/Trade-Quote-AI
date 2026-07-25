import { describe, expect, it } from "vitest";
import { formatMoney, parseMoneyToMinor } from "@/lib/money";

describe("formatMoney", () => {
  it("formats cents as dollars with two decimals", () => {
    expect(formatMoney(151160, "USD")).toBe("$1,511.60");
  });

  it("formats zero correctly", () => {
    expect(formatMoney(0, "USD")).toBe("$0.00");
  });

  it("uses the GBP symbol", () => {
    expect(formatMoney(100000, "GBP")).toBe("£1,000.00");
  });

  it("defaults to USD when currency is omitted", () => {
    expect(formatMoney(500)).toBe("$5.00");
  });
});

describe("parseMoneyToMinor", () => {
  it("parses a plain dollar string", () => {
    expect(parseMoneyToMinor("19.99")).toBe(1999);
  });

  it("strips commas and currency symbols", () => {
    expect(parseMoneyToMinor("$1,234.56")).toBe(123456);
  });

  it("treats an empty string as 0", () => {
    expect(parseMoneyToMinor("")).toBe(0);
  });

  it("round-trips with formatMoney", () => {
    const minor = parseMoneyToMinor("850");
    expect(formatMoney(minor)).toBe("$850.00");
  });
});
