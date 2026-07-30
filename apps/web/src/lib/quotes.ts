import { z } from "zod";
import { apiFetch } from "@/lib/api-client";
import { parseMoneyToMinor } from "@/lib/money";

/** ---- Wire types (mirror services/quote-service/app/interface/schemas.py) ---- */

export interface LineItem {
  id: string;
  kind: "material" | "labor" | "equipment" | "consumable" | "rental" | "package";
  description: string;
  quantity: number;
  unit: string;
  unit_cost_minor: number;
  markup_bps: number;
  unit_price_minor: number;
  line_total_minor: number;
  is_optional: boolean;
  sort_order: number;
}

export interface Quote {
  id: string;
  customer_id: string;
  property_id: string | null;
  number: string;
  title: string | null;
  status: "draft" | "sent" | "viewed" | "accepted" | "rejected" | "expired" | "archived";
  currency: string;
  tax_rate_bps: number;
  subtotal_minor: number;
  tax_minor: number;
  total_minor: number;
  current_version: number;
  valid_until: string | null;
  created_at: string;
  updated_at: string;
  line_items: LineItem[];
}

/** ---- Form schema (dollars/percent — human units) — pure, unit-tested ---- */

export const lineItemFormSchema = z.object({
  description: z.string().min(1, "Description is required"),
  quantity: z.coerce.number().positive("Must be greater than 0"),
  unit: z.string().min(1).default("each"),
  unitPriceDollars: z.coerce.number().min(0, "Must be 0 or more"),
});

export const newQuoteFormSchema = z.object({
  customerId: z.string().uuid("Select a customer"),
  title: z.string().max(255).optional().or(z.literal("")),
  taxRatePercent: z.coerce.number().min(0).max(100).default(0),
  lineItems: z.array(lineItemFormSchema).min(1, "Add at least one line item"),
});

export type LineItemFormInput = z.infer<typeof lineItemFormSchema>;
export type NewQuoteFormInput = z.infer<typeof newQuoteFormSchema>;

/** Maps the human-units form to quote-service's wire DTO (cents + basis points). */
export function toQuoteCreatePayload(form: NewQuoteFormInput) {
  return {
    customer_id: form.customerId,
    title: form.title || null,
    tax_rate_bps: Math.round(form.taxRatePercent * 100),
    initial_line_items: form.lineItems.map((item, index) => ({
      description: item.description,
      quantity: item.quantity,
      unit: item.unit,
      unit_cost_minor: 0,
      markup_bps: 0,
      unit_price_minor: parseMoneyToMinor(String(item.unitPriceDollars)),
      sort_order: index,
    })),
  };
}

/** Live subtotal preview while editing the form — mirrors the server's math. */
export function calculateFormSubtotalMinor(lineItems: LineItemFormInput[]): number {
  return lineItems.reduce((sum, item) => {
    const unitPriceMinor = parseMoneyToMinor(String(item.unitPriceDollars || 0));
    return sum + Math.round((item.quantity || 0) * unitPriceMinor);
  }, 0);
}

/** Maps a quote status to a Badge variant — pure, unit-tested. */
export function statusBadgeVariant(
  status: Quote["status"],
): "default" | "secondary" | "destructive" | "success" | "warning" {
  switch (status) {
    case "accepted":
      return "success";
    case "sent":
    case "viewed":
      return "default";
    case "rejected":
    case "expired":
      return "destructive";
    case "archived":
      return "secondary";
    case "draft":
    default:
      return "warning";
  }
}

/** ---- API calls ---- */

interface QuoteListResponse {
  items?: Quote[];
}

export function listQuotes(token: string, limit?: number): Promise<Quote[]> {
  const qs = limit ? `?limit=${limit}` : "";
  return apiFetch<Quote[] | QuoteListResponse>(`/v1/quotes${qs}`, { token }).then((res) =>
    Array.isArray(res) ? res : (res.items ?? []),
  );
}

export function getQuote(token: string, quoteId: string): Promise<Quote> {
  return apiFetch<Quote>(`/v1/quotes/${quoteId}`, { token });
}

export function createQuote(token: string, form: NewQuoteFormInput): Promise<Quote> {
  return apiFetch<Quote>("/v1/quotes", { method: "POST", token, body: toQuoteCreatePayload(form) });
}

export function addLineItem(
  token: string,
  quoteId: string,
  item: LineItemFormInput,
): Promise<LineItem> {
  return apiFetch<LineItem>(`/v1/quotes/${quoteId}/line-items`, {
    method: "POST",
    token,
    body: {
      description: item.description,
      quantity: item.quantity,
      unit: item.unit,
      unit_cost_minor: 0,
      markup_bps: 0,
      unit_price_minor: parseMoneyToMinor(String(item.unitPriceDollars)),
    },
  });
}

export function sendQuote(token: string, quoteId: string, channel = "email"): Promise<Quote> {
  return apiFetch<Quote>(`/v1/quotes/${quoteId}/send`, {
    method: "POST",
    token,
    body: { channel },
  });
}

export function acceptQuote(token: string, quoteId: string): Promise<Quote> {
  return apiFetch<Quote>(`/v1/quotes/${quoteId}/accept`, { method: "POST", token });
}

export function rejectQuote(token: string, quoteId: string, reason?: string): Promise<Quote> {
  return apiFetch<Quote>(`/v1/quotes/${quoteId}/reject`, {
    method: "POST",
    token,
    body: { reason: reason || null },
  });
}
