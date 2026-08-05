"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { describeAiSubmitError } from "@/lib/ai";
import {
  addMissingItemToQuote,
  analyzePricing,
  applyMarkupSuggestion,
  findMissingItems,
  formatBpsPercent,
  priorityBadgeVariant,
  type MissingItem,
  type MissingItemsResult,
  type PricingAnalysisResult,
} from "@/lib/copilot";
import { formatMoney } from "@/lib/money";
import type { Quote } from "@/lib/quotes";

interface CopilotPanelProps {
  token: string;
  quote: Quote;
}

/** Identity for a suggested item within one result set.
 *
 * The model can legitimately return two items with the same name (say two
 * different conduit runs), so the index is part of the identity — otherwise
 * adding one would mark the other as already added. Exported and unit-tested
 * because getting this wrong is silent: the UI would just look right.
 */
export function missingItemKey(item: Pick<MissingItem, "item_name">, index: number): string {
  return `${index}:${item.item_name}`;
}

/**
 * On-demand AI Copilot actions for a saved quote (T202b). Nothing here runs
 * automatically — every analysis is a metered LLM call against the tenant's
 * daily spend cap, so each section is gated behind its own button.
 */
export function CopilotPanel({ token, quote }: CopilotPanelProps) {
  const queryClient = useQueryClient();

  function invalidateQuote() {
    queryClient.invalidateQueries({ queryKey: ["quotes", quote.id] });
    queryClient.invalidateQueries({ queryKey: ["quotes"] });
  }

  const [pricingError, setPricingError] = React.useState<string | null>(null);
  const [pricing, setPricing] = React.useState<PricingAnalysisResult | null>(null);

  const analyzeMutation = useMutation({
    mutationFn: () => analyzePricing(token, quote.id),
    onSuccess: (result) => {
      setPricing(result);
      setPricingError(null);
    },
    onError: (err) => setPricingError(describeAiSubmitError(err)),
  });

  // Keyed by line item so one failing row doesn't paint an error over the
  // whole panel — the previous shared `pricingError` reported a row-3 failure
  // at the top of the section.
  const [applyErrors, setApplyErrors] = React.useState<Record<string, string>>({});

  const applyMutation = useMutation({
    mutationFn: (vars: { lineItemId: string; markupBps: number }) =>
      applyMarkupSuggestion(token, quote.id, vars.lineItemId, vars.markupBps),
    onSuccess: (_data, vars) => {
      setApplyErrors((prev) => {
        const next = { ...prev };
        delete next[vars.lineItemId];
        return next;
      });
      invalidateQuote();
    },
    onError: (err, vars) =>
      setApplyErrors((prev) => ({ ...prev, [vars.lineItemId]: describeAiSubmitError(err) })),
  });

  const [jobDescription, setJobDescription] = React.useState("");
  const [missingError, setMissingError] = React.useState<string | null>(null);
  const [missingResult, setMissingResult] = React.useState<MissingItemsResult | null>(null);

  // Which suggestions are already in the quote. Adding is a POST and so is
  // *not* idempotent — without this, a second click silently creates a second
  // $0 line item, and the added line renders above this panel where a
  // contractor who doesn't scroll never sees it happen.
  const [addedKeys, setAddedKeys] = React.useState<ReadonlySet<string>>(new Set());
  const [addErrors, setAddErrors] = React.useState<Record<string, string>>({});

  const findMissingMutation = useMutation({
    mutationFn: () => findMissingItems(token, quote.id, jobDescription || undefined),
    onSuccess: (result) => {
      setMissingResult(result);
      setMissingError(null);
      // A fresh analysis is a fresh list — keys are positional, so carrying
      // the old set over would mark unrelated rows as already added.
      setAddedKeys(new Set());
      setAddErrors({});
    },
    onError: (err) => setMissingError(describeAiSubmitError(err)),
  });

  const addMissingMutation = useMutation({
    mutationFn: (vars: { item: MissingItem; key: string }) =>
      addMissingItemToQuote(token, quote.id, vars.item),
    onSuccess: (_data, vars) => {
      setAddedKeys((prev) => new Set(prev).add(vars.key));
      setAddErrors((prev) => {
        const next = { ...prev };
        delete next[vars.key];
        return next;
      });
      invalidateQuote();
    },
    onError: (err, vars) =>
      setAddErrors((prev) => ({ ...prev, [vars.key]: describeAiSubmitError(err) })),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI Copilot</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Pricing analysis</h3>
            <Button
              type="button"
              size="sm"
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending || quote.line_items.length === 0}
            >
              {analyzeMutation.isPending ? "Analyzing…" : "Analyze Pricing"}
            </Button>
          </div>
          {pricingError && <p className="text-sm text-destructive">{pricingError}</p>}
          {pricing && (
            <div className="space-y-3 rounded-md border border-dashed border-input p-3">
              <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <div>
                  <p className="text-muted-foreground">Cost</p>
                  <p className="font-medium">
                    {formatMoney(pricing.margin.total_cost_minor, quote.currency)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Revenue</p>
                  <p className="font-medium">
                    {formatMoney(pricing.margin.total_revenue_minor, quote.currency)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Gross margin</p>
                  <p className="font-medium">{formatBpsPercent(pricing.margin.gross_margin_bps)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Avg. markup</p>
                  <p className="font-medium">
                    {formatBpsPercent(pricing.margin.average_markup_bps)}
                  </p>
                </div>
              </div>
              <p className="text-sm">{pricing.margin.recommendation}</p>

              {pricing.suggestions.length > 0 && (
                <ul className="space-y-2">
                  {pricing.suggestions.map((suggestion) => {
                    const lineItem = quote.line_items.find(
                      (item) => item.id === suggestion.line_item_id,
                    );
                    const isLowMargin = pricing.margin.low_margin_item_ids.includes(
                      suggestion.line_item_id,
                    );
                    return (
                      <li key={suggestion.line_item_id} className="rounded-md border p-2 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">
                            {lineItem?.description ?? suggestion.line_item_id}
                          </span>
                          {isLowMargin && <Badge variant="destructive">Low margin</Badge>}
                        </div>
                        <p className="text-muted-foreground">
                          Current markup {formatBpsPercent(suggestion.current_markup_bps)}
                          {suggestion.suggested_markup_bps !== null && (
                            <> → suggested {formatBpsPercent(suggestion.suggested_markup_bps)}</>
                          )}
                        </p>
                        <p className="text-muted-foreground">{suggestion.reasoning}</p>
                        {applyErrors[suggestion.line_item_id] && (
                          <p className="mt-1 text-destructive">
                            {applyErrors[suggestion.line_item_id]}
                          </p>
                        )}
                        {suggestion.suggested_markup_bps !== null && (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="mt-2"
                            onClick={() =>
                              applyMutation.mutate({
                                lineItemId: suggestion.line_item_id,
                                markupBps: suggestion.suggested_markup_bps as number,
                              })
                            }
                            // Scoped to the row actually in flight — react-query
                            // exposes the in-flight variables, so one mutation
                            // instance still gives per-row feedback.
                            disabled={
                              applyMutation.isPending &&
                              applyMutation.variables?.lineItemId === suggestion.line_item_id
                            }
                          >
                            {applyMutation.isPending &&
                            applyMutation.variables?.lineItemId === suggestion.line_item_id
                              ? "Applying…"
                              : "Apply suggested markup"}
                          </Button>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="space-y-3 border-t pt-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Missing items</h3>
            <Button
              type="button"
              size="sm"
              onClick={() => findMissingMutation.mutate()}
              disabled={findMissingMutation.isPending}
            >
              {findMissingMutation.isPending ? "Checking…" : "Find Missing Items"}
            </Button>
          </div>
          <Label htmlFor="copilotJobDescription">Job description (optional)</Label>
          <textarea
            id="copilotJobDescription"
            className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="Describe the job for better results"
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
          />
          {missingError && <p className="text-sm text-destructive">{missingError}</p>}
          {missingResult && (
            <div className="space-y-3 rounded-md border border-dashed border-input p-3">
              <p className="text-sm font-medium">
                Completeness: {missingResult.completeness_score}/100
              </p>
              <p className="text-sm text-muted-foreground">{missingResult.summary}</p>
              {missingResult.missing.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing missing found.</p>
              ) : (
                <ul className="space-y-2">
                  {missingResult.missing.map((item, index) => {
                    const key = missingItemKey(item, index);
                    const isAdded = addedKeys.has(key);
                    const isAdding =
                      addMissingMutation.isPending && addMissingMutation.variables?.key === key;
                    return (
                      <li key={key} className="rounded-md border p-2 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">{item.description}</span>
                          <Badge
                            variant={priorityBadgeVariant(item.priority)}
                            className="capitalize"
                          >
                            {item.priority}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground">
                          {item.estimated_quantity} {item.unit} — {item.reasoning}
                        </p>
                        {addErrors[key] && (
                          <p className="mt-1 text-destructive">{addErrors[key]}</p>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="mt-2"
                          onClick={() => addMissingMutation.mutate({ item, key })}
                          // Stays disabled after success: this is a POST, so a
                          // second click would add a second $0 line.
                          disabled={isAdded || isAdding}
                        >
                          {isAdded ? "✓ Added to quote" : isAdding ? "Adding…" : "Add to Quote"}
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
