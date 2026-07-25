export interface CurrencyTotal {
  currency: string;
  accepted_value_minor: number;
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

/** Headlines the "Accepted Value" card. Currencies are never summed (see dashboard spec D6). */
export function pickPrimaryTotal(totals: CurrencyTotal[]): CurrencyTotal | null {
  return totals[0] ?? null;
}
