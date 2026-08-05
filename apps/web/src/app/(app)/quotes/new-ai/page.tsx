"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { listCustomers } from "@/lib/customers";
import {
  describeAiSubmitError,
  submitTextToQuote,
  submitVoiceToQuote,
  type QuoteDraft,
} from "@/lib/ai";
import { useVoiceRecorder } from "@/components/ai/voice-recorder";

const AI_DRAFT_STORAGE_PREFIX = "ai-draft:";

type EntryMode = "type" | "record";

export default function NewAiQuotePage() {
  const token = useAuthGuard();
  const router = useRouter();
  const [mode, setMode] = React.useState<EntryMode>("type");
  const [customerId, setCustomerId] = React.useState("");
  const [text, setText] = React.useState("");
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const recorder = useVoiceRecorder();

  const { data: customers } = useQuery({
    queryKey: ["customers"],
    queryFn: () => listCustomers(token as string),
    enabled: !!token,
  });

  function onDraftCreated(draft: QuoteDraft) {
    sessionStorage.setItem(`${AI_DRAFT_STORAGE_PREFIX}${draft.quote_id}`, JSON.stringify(draft));
    router.push(`/quotes/${draft.quote_id}?from=ai`);
  }

  const textMutation = useMutation({
    mutationFn: () => submitTextToQuote(token as string, { text, customer_id: customerId }),
    onSuccess: onDraftCreated,
    onError: (err) => setSubmitError(describeAiSubmitError(err)),
  });

  const voiceMutation = useMutation({
    mutationFn: () => {
      if (!recorder.audioBlob) throw new Error("no recording captured");
      return submitVoiceToQuote(token as string, {
        audioBlob: recorder.audioBlob,
        customer_id: customerId,
      });
    },
    onSuccess: onDraftCreated,
    onError: (err) => setSubmitError(describeAiSubmitError(err)),
  });

  function handleTextSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    textMutation.mutate();
  }

  function handleVoiceSubmit() {
    setSubmitError(null);
    voiceMutation.mutate();
  }

  const isPending = textMutation.isPending || voiceMutation.isPending;
  const canSubmitText = !!customerId && text.trim().length >= 10;
  const canSubmitVoice = !!customerId && !!recorder.audioBlob;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Describe the Job</h1>
        <p className="text-muted-foreground">
          Type or record a description — we&apos;ll draft a priced quote from it.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Customer</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label htmlFor="customerId">Customer</Label>
            <Select
              id="customerId"
              value={customerId}
              onChange={(event) => setCustomerId(event.target.value)}
            >
              <option value="">Select a customer…</option>
              {customers?.items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Job Description</CardTitle>
          <div className="flex gap-2 pt-2">
            <Button
              type="button"
              variant={mode === "type" ? "default" : "outline"}
              onClick={() => setMode("type")}
            >
              Type
            </Button>
            <Button
              type="button"
              variant={mode === "record" ? "default" : "outline"}
              onClick={() => setMode("record")}
            >
              Record
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {mode === "type" && (
            <form onSubmit={handleTextSubmit} className="space-y-4">
              <textarea
                rows={6}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="Replace the panel with a 200 amp and put twelve LED cans in the kitchen…"
                value={text}
                onChange={(event) => setText(event.target.value)}
                disabled={isPending}
              />
              <Button type="submit" disabled={!canSubmitText || isPending}>
                {textMutation.isPending ? "Drafting…" : "Draft Quote"}
              </Button>
            </form>
          )}

          {mode === "record" && (
            <div className="space-y-4">
              {recorder.state === "idle" && (
                <Button type="button" onClick={() => recorder.start()}>
                  Start Recording
                </Button>
              )}
              {recorder.state === "requesting" && (
                <p className="text-sm text-muted-foreground">Requesting microphone access…</p>
              )}
              {recorder.state === "recording" && (
                <Button type="button" variant="outline" onClick={() => recorder.stop()}>
                  Stop Recording
                </Button>
              )}
              {recorder.state === "recorded" && (
                <div className="flex items-center gap-2">
                  <p className="text-sm text-muted-foreground">Recording captured.</p>
                  <Button type="button" variant="outline" onClick={() => recorder.reset()}>
                    Re-record
                  </Button>
                </div>
              )}
              {recorder.state === "denied" && (
                <div className="space-y-2">
                  <p className="text-sm text-destructive">
                    Microphone access was denied. Allow microphone access in your browser to record,
                    or use the Type tab instead.
                  </p>
                  <Button type="button" variant="outline" onClick={() => recorder.start()}>
                    Try Again
                  </Button>
                </div>
              )}
              <Button
                type="button"
                onClick={handleVoiceSubmit}
                disabled={!canSubmitVoice || isPending}
              >
                {voiceMutation.isPending ? "Drafting…" : "Draft Quote"}
              </Button>
            </div>
          )}

          {submitError && <p className="text-sm text-destructive">{submitError}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
