import { apiFetch, ApiError } from "@/lib/api-client";
import type { LineItem, Quote } from "@/lib/quotes";

/** Mirrors ai-service's app/domain/models.py Trade enum — a closed set (see M15 spec D-notes). */
export type Trade =
  | "electrical"
  | "plumbing"
  | "hvac"
  | "solar"
  | "roofing"
  | "flooring"
  | "landscaping"
  | "painting"
  | "cleaning"
  | "general";

export const TRADES: { value: Trade; label: string }[] = [
  { value: "electrical", label: "Electrical" },
  { value: "plumbing", label: "Plumbing" },
  { value: "hvac", label: "HVAC" },
  { value: "solar", label: "Solar" },
  { value: "roofing", label: "Roofing" },
  { value: "flooring", label: "Flooring" },
  { value: "landscaping", label: "Landscaping" },
  { value: "painting", label: "Painting" },
  { value: "cleaning", label: "Cleaning" },
  { value: "general", label: "General" },
];

/** Mirrors ai-service's TaskCategory — 1:1 onto the 3 kinds the extractor can produce. */
export type TaskCategory = "material" | "labor" | "equipment";

export interface ExtractedTask {
  description: string;
  category: TaskCategory;
  item_name: string;
  quantity: number;
  unit: string;
  pricebook_item_id: string | null;
  match_confidence: number | null;
  unit_cost_minor: number | null;
}

export interface QuoteDraft {
  quote_id: string;
  trade: Trade;
  summary: string;
  notes: string;
  tasks: ExtractedTask[];
  unmatched_count: number;
  model_id: string;
  tokens_used: number;
  input_kind: string;
  transcript: string | null;
  language: string | null;
}

export interface TextToQuoteInput {
  text: string;
  customer_id: string;
  property_id?: string | null;
  title?: string | null;
  trade_hint?: string | null;
  tax_rate_bps?: number;
  default_markup_bps?: number;
}

export function submitTextToQuote(token: string, input: TextToQuoteInput): Promise<QuoteDraft> {
  return apiFetch<QuoteDraft>("/v1/ai/text-to-quote", { method: "POST", token, body: input });
}

export interface VoiceToQuoteInput {
  audioBlob: Blob;
  customer_id: string;
  property_id?: string | null;
  title?: string | null;
  trade_hint?: string | null;
  tax_rate_bps?: number;
  default_markup_bps?: number;
}

export function submitVoiceToQuote(token: string, input: VoiceToQuoteInput): Promise<QuoteDraft> {
  const form = new FormData();
  form.append("audio", input.audioBlob, "recording.webm");
  form.append("customer_id", input.customer_id);
  if (input.property_id) form.append("property_id", input.property_id);
  if (input.title) form.append("title", input.title);
  if (input.trade_hint) form.append("trade_hint", input.trade_hint);
  if (input.tax_rate_bps != null) form.append("tax_rate_bps", String(input.tax_rate_bps));
  if (input.default_markup_bps != null) {
    form.append("default_markup_bps", String(input.default_markup_bps));
  }
  return apiFetch<QuoteDraft>("/v1/ai/voice-to-quote", { method: "POST", token, body: form });
}

export interface ScopeTaskInput {
  description: string;
  category: TaskCategory;
  item_name: string;
  quantity: number;
  unit: string;
}

export interface ScopeWriterInput {
  trade: Trade;
  summary: string;
  tasks: ScopeTaskInput[];
  notes?: string;
  tone?: string;
}

export interface ScopeWriterResult {
  scope_text: string;
  model_id: string;
  tokens_used: number;
}

export function generateScopeText(
  token: string,
  input: ScopeWriterInput,
): Promise<ScopeWriterResult> {
  return apiFetch<ScopeWriterResult>("/v1/ai/scope-writer", { method: "POST", token, body: input });
}

/**
 * Maps quote-service's 6-value ItemKind to ai-service's 3-value TaskCategory.
 * RENTAL/PACKAGE/CONSUMABLE fall back to "material", the closest of the three
 * (a named, deliberate lossy mapping — see M15 web UI spec §4.3).
 */
export function lineItemKindToTaskCategory(kind: LineItem["kind"]): TaskCategory {
  if (kind === "labor") return "labor";
  if (kind === "equipment") return "equipment";
  return "material";
}

/** Maps a quote's existing line items into the scope-writer's task-list shape. */
export function quoteLineItemsToScopeTasks(quote: Quote): ScopeTaskInput[] {
  return quote.line_items.map((item) => ({
    description: item.description,
    category: lineItemKindToTaskCategory(item.kind),
    item_name: item.description,
    quantity: item.quantity,
    unit: item.unit,
  }));
}

/** Maps a submit failure to an actionable, specific message — never a bare status code. */
export function describeAiSubmitError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 413:
        return "That recording is too long. Try a shorter one.";
      case 400:
        return "That audio format isn't supported. Try recording again.";
      case 429:
        return "You've reached today's AI usage limit. Try again tomorrow.";
      case 502:
        return "The AI service is temporarily unavailable. Try again shortly.";
      case 422:
        return "Couldn't make sense of that description — try adding more detail.";
      default:
        return err.message || "Something went wrong. Please try again.";
    }
  }
  return "Something went wrong. Please try again.";
}

/**
 * True when a rendered line-item row should show an "Unmatched" badge. Only
 * meaningful order-matched against the quote's line_items[] immediately after
 * AI creation — see M15 web UI spec §4.2.
 */
export function isUnmatchedTask(task: ExtractedTask): boolean {
  return task.pricebook_item_id === null;
}
