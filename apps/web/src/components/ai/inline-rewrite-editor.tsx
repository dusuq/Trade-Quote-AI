"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { describeAiSubmitError } from "@/lib/ai";
import { rewriteTexts, updateLineItemDescription } from "@/lib/copilot";

interface InlineRewriteEditorProps {
  token: string;
  quoteId: string;
  lineItemId: string;
  initialText: string;
  onSaved: () => void;
  onCancel: () => void;
}

/**
 * Replaces a line item's description cell while active. "Rewrite" calls the
 * copilot (advisory only — text stays in this textarea for editing); "Save"
 * is the only action that writes to quote-service, so nothing is ever
 * auto-applied (M16 web UI spec §5).
 */
export function InlineRewriteEditor({
  token,
  quoteId,
  lineItemId,
  initialText,
  onSaved,
  onCancel,
}: InlineRewriteEditorProps) {
  const [text, setText] = React.useState(initialText);
  const [error, setError] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const rewriteMutation = useMutation({
    mutationFn: () => rewriteTexts(token, [text]),
    onSuccess: (result) => {
      setText(result.rewritten[0]);
      setError(null);
    },
    onError: (err) => setError(describeAiSubmitError(err)),
  });

  const saveMutation = useMutation({
    mutationFn: () => updateLineItemDescription(token, quoteId, lineItemId, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotes", quoteId] });
      onSaved();
    },
    onError: (err) => setError(describeAiSubmitError(err)),
  });

  const isBusy = rewriteMutation.isPending || saveMutation.isPending;

  return (
    <div className="space-y-2">
      <textarea
        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => rewriteMutation.mutate()}
          disabled={isBusy || text.trim().length === 0}
        >
          {rewriteMutation.isPending ? "Rewriting…" : "Rewrite"}
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={isBusy || text.trim().length === 0}
        >
          {saveMutation.isPending ? "Saving…" : "Save"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={isBusy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
