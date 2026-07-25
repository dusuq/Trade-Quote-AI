const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  CAD: "$",
  AUD: "$",
  NZD: "$",
  GBP: "£",
};

/** Integer minor units (cents) + ISO-4217 currency -> "$1,234.56". Never floats. */
export function formatMoney(amountMinor: number, currency = "USD"): string {
  const symbol = CURRENCY_SYMBOLS[currency] ?? "";
  const amount = amountMinor / 100;
  return `${symbol}${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Parse a user-entered dollar string ("1,234.56") into integer minor units. */
export function parseMoneyToMinor(input: string): number {
  const cleaned = input.replace(/[^0-9.-]/g, "");
  const dollars = Number.parseFloat(cleaned || "0");
  return Math.round(dollars * 100);
}
