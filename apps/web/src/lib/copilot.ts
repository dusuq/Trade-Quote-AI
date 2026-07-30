import { apiFetch } from "@/lib/api-client";
import { AI_REQUEST_TIMEOUT_MS } from "@/lib/ai";
import type { LineItem } from "@/lib/quotes";

export interface PricingSuggestion {
  line_item_id: string;
  current_unit_cost_minor: number;
  current_markup_bps: number;
  current_unit_price_minor: number;
  suggested_markup_bps: number | null;
  pricebook_unit_cost_minor: number | null;
  reasoning: string;
}

export interface MarginAnalysis {
  total_cost_minor: number;
  total_revenue_minor: number;
  gross_margin_bps: number;
  average_markup_bps: number;
  low_margin_item_ids: string[];
  recommendation: string;
}

export interface PricingAnalysisResult {
  quote_id: string;
  suggestions: PricingSuggestion[];
  margin: MarginAnalysis;
  model_id: string;
  tokens_used: number;
}

export function analyzePricing(token: string, quoteId: string): Promise<PricingAnalysisResult> {
  return apiFetch<PricingAnalysisResult>("/v1/ai/copilot/analyze-pricing", {
    method: "POST",
    token,
    body: { quote_id: quoteId },
    timeoutMs: AI_REQUEST_TIMEOUT_MS,
  });
}

export type MissingItemCategory = "material" | "labor" | "equipment";
export type MissingItemPriority = "critical" | "recommended" | "optional";

export interface MissingItem {
  description: string;
  category: MissingItemCategory;
  item_name: string;
  estimated_quantity: number;
  unit: string;
  reasoning: string;
  priority: MissingItemPriority;
}

export interface MissingItemsResult {
  quote_id: string;
  trade: string;
  completeness_score: number;
  summary: string;
  missing: MissingItem[];
  model_id: string;
  tokens_used: number;
}

export function findMissingItems(
  token: string,
  quoteId: string,
  jobDescription?: string,
): Promise<MissingItemsResult> {
  return apiFetch<MissingItemsResult>("/v1/ai/copilot/missing-items", {
    method: "POST",
    token,
    body: { quote_id: quoteId, job_description: jobDescription || undefined },
    timeoutMs: AI_REQUEST_TIMEOUT_MS,
  });
}

export interface CopilotRewriteResult {
  rewritten: string[];
  model_id: string;
  tokens_used: number;
}

export function rewriteTexts(
  token: string,
  texts: string[],
  tone = "professional",
  contextHint?: string,
): Promise<CopilotRewriteResult> {
  return apiFetch<CopilotRewriteResult>("/v1/ai/copilot/rewrite", {
    method: "POST",
    token,
    body: { texts, tone, context_hint: contextHint },
    timeoutMs: AI_REQUEST_TIMEOUT_MS,
  });
}

/** The three missing-item category values are already valid quote-service
 * ItemKind values — a direct passthrough, not a lossy mapping. */
export function missingItemCategoryToItemKind(category: MissingItemCategory): LineItem["kind"] {
  return category;
}

export function addMissingItemToQuote(
  token: string,
  quoteId: string,
  item: MissingItem,
): Promise<LineItem> {
  return apiFetch<LineItem>(`/v1/quotes/${quoteId}/line-items`, {
    method: "POST",
    token,
    body: {
      description: item.description,
      kind: missingItemCategoryToItemKind(item.category),
      quantity: item.estimated_quantity,
      unit: item.unit,
      unit_cost_minor: 0,
      markup_bps: 0,
      unit_price_minor: 0,
    },
  });
}

export function applyMarkupSuggestion(
  token: string,
  quoteId: string,
  lineItemId: string,
  markupBps: number,
): Promise<LineItem> {
  return apiFetch<LineItem>(`/v1/quotes/${quoteId}/line-items/${lineItemId}`, {
    method: "PUT",
    token,
    body: { markup_bps: markupBps },
  });
}

export function updateLineItemDescription(
  token: string,
  quoteId: string,
  lineItemId: string,
  description: string,
): Promise<LineItem> {
  return apiFetch<LineItem>(`/v1/quotes/${quoteId}/line-items/${lineItemId}`, {
    method: "PUT",
    token,
    body: { description },
  });
}

/** Badge variant for a missing item's priority — pure, unit-tested. */
export function priorityBadgeVariant(
  priority: MissingItemPriority,
): "destructive" | "warning" | "secondary" {
  switch (priority) {
    case "critical":
      return "destructive";
    case "recommended":
      return "warning";
    case "optional":
      return "secondary";
  }
}

/** Basis points -> a one-decimal percent string, e.g. 2050 -> "20.5%". */
export function formatBpsPercent(bps: number): string {
  return `${(bps / 100).toFixed(1)}%`;
}
