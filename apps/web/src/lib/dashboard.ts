import { apiFetch } from "@/lib/api-client";
import { formatMoney } from "@/lib/money";

export interface CurrencyTotal {
  currency: string;
  accepted_value_minor: number;
}

export interface QuoteSummary {
  timezone: string;
  range: "mtd" | "ytd";
  range_start: string;
  range_end: string;
  quotes_today: number;
  pending_count: number;
  accepted_count: number;
  decided_count: number;
  conversion_bps: number;
  totals: CurrencyTotal[];
}

/** IANA zone name for the current browser, e.g. "Australia/Sydney". */
export function resolveBrowserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** "—" when nothing has been decided yet — a literal 0.0% would misstate an empty pipeline. */
export function formatConversion(conversionBps: number, decidedCount: number): string {
  if (decidedCount === 0) return "—";
  return `${(conversionBps / 100).toFixed(1)}%`;
}

/**
 * Formats the "Accepted Value" card as one display line per currency — never a
 * cross-currency sum, and never only the first entry (spec D6). A tenant with
 * A$200 and US$500 accepted must see both, or the card understates their month.
 *
 * With two or more currencies each line carries its ISO code, because
 * `CURRENCY_SYMBOLS` maps USD, CAD, AUD and NZD all to "$" — the symbol alone
 * cannot tell the reader which currency a figure is in. A single-currency tenant
 * (the overwhelming majority) gets the bare formatted amount, unchanged.
 *
 * Returns [] for empty totals; the caller decides how to render "nothing
 * accepted", since the response carries no currency to format a zero in.
 */
export function formatAcceptedTotals(totals: CurrencyTotal[]): string[] {
  if (totals.length === 1) {
    return [formatMoney(totals[0].accepted_value_minor, totals[0].currency)];
  }
  return totals.map(
    (total) => `${formatMoney(total.accepted_value_minor, total.currency)} ${total.currency}`,
  );
}

export function fetchQuoteSummary(
  token: string,
  tz: string,
  range: "mtd" | "ytd" = "mtd",
): Promise<QuoteSummary> {
  const qs = `?tz=${encodeURIComponent(tz)}&range=${range}`;
  return apiFetch<QuoteSummary>(`/v1/quotes/summary${qs}`, { token });
}
