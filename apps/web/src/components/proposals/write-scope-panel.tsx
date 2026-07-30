"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { generateScopeText, quoteLineItemsToScopeTasks, TRADES, type Trade } from "@/lib/ai";
import type { Quote } from "@/lib/quotes";

interface WriteScopePanelProps {
  token: string;
  quote: Quote;
  onGenerated: (scopeText: string) => void;
  onClose: () => void;
}

/**
 * Inline panel for the proposal editor's "Write Scope" action (T201b). Asks
 * for trade + a one-line job summary rather than guessing (M15 web UI spec
 * D4) — silently defaulting to "general" would genericize the trade-aware
 * prose that's this endpoint's entire value.
 */
export function WriteScopePanel({ token, quote, onGenerated, onClose }: WriteScopePanelProps) {
  const [trade, setTrade] = React.useState<Trade>("general");
  const [summary, setSummary] = React.useState(quote.title ?? "");
  const [tone, setTone] = React.useState("professional");
  const [error, setError] = React.useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      generateScopeText(token, {
        trade,
        summary,
        tasks: quoteLineItemsToScopeTasks(quote),
        tone,
      }),
    onSuccess: (result) => {
      onGenerated(result.scope_text);
      onClose();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Unable to generate scope text.");
    },
  });

  const canGenerate = summary.trim().length > 0 && quote.line_items.length > 0;

  return (
    <div className="space-y-4 rounded-md border border-dashed border-input p-4">
      <div className="space-y-2">
        <Label htmlFor="writeScopeTrade">Trade</Label>
        <Select
          id="writeScopeTrade"
          value={trade}
          onChange={(event) => setTrade(event.target.value as Trade)}
        >
          {TRADES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="writeScopeSummary">Job summary</Label>
        <input
          id="writeScopeSummary"
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="One line describing the job"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="writeScopeTone">Tone</Label>
        <Select id="writeScopeTone" value={tone} onChange={(event) => setTone(event.target.value)}>
          <option value="professional">Professional</option>
          <option value="friendly">Friendly</option>
          <option value="formal">Formal</option>
        </Select>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex gap-2">
        <Button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={!canGenerate || mutation.isPending}
        >
          {mutation.isPending ? "Generating…" : "Generate"}
        </Button>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
