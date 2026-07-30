# T201b — M15 AI Quote Assistant Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `apps/web` to the already-signed-off `services/ai-service` (T201/T202) backend — a
"describe the job" entry point (text or voice), an AI-draft review banner on the resulting quote,
and a "Write Scope" action on the proposal editor.

**Architecture:** A new `apps/web/src/lib/ai.ts` data layer talks to the existing `/v1/ai/*` gateway
routes. A new `/quotes/new-ai` page (parallel to the existing manual form) submits text or a native
`MediaRecorder` recording, which the backend turns into a real draft quote in one call; the web app
hands the extraction result to the quote detail page via a one-time `sessionStorage` key so it can
render a review banner and flag unmatched lines. A "Write Scope" panel on the proposal editor calls
the same backend's `scope-writer` endpoint to generate prose from the quote's own line items.

**Tech Stack:** Next.js 15 + TanStack Query + `react-hook-form`/`zod` + Vitest (existing stack, no
new dependencies) + the browser's native `MediaRecorder` API.

**Spec:** [docs/modules/M15-ai-quote-assistant-web-ui.md](M15-ai-quote-assistant-web-ui.md) — read it
first; this plan implements decisions D1–D6 verbatim.

## Global Constraints

- No backend changes — `services/ai-service` and the gateway's `/v1/ai` proxy are already complete
  and CTO-signed-off (spec, dependencies).
- Money stays integer minor units wherever it appears; this feature introduces no new money fields
  of its own (it consumes/produces text, not prices), but existing `Quote`/`LineItem` money fields
  must never be reformatted as floats.
- Submit mutations disable their button immediately on click and never auto-retry (D5) — this app's
  `QueryClient` overrides only `queries.retry`, so mutations already inherit TanStack Query's
  library default of zero automatic retries; do not add a `retry` option to any mutation here.
- `MediaRecorder`'s output mime type must not be second-guessed or transcoded client-side — both
  `audio/webm` and `audio/mp4` are already on the backend's whitelist (verified in spec D3).
- `pnpm typecheck` and `pnpm test` must stay clean, including every pre-existing test, after every
  task.
- No component-test infrastructure exists in this repo — UI-only tasks (pages, the recorder hook,
  the scope panel) are verified via `pnpm typecheck` + `pnpm build`, not new unit tests; pure
  functions and API-call functions in `ai.ts` do get unit tests.

---

## File Structure

```
apps/web/src/lib/
  api-client.ts                          EDIT — apiFetch supports a FormData body
  api-client.test.ts                     EDIT — +FormData test
  ai.ts                                  NEW — wire types, API calls, pure helpers
  ai.test.ts                             NEW
  quotes.ts                              EDIT — LineItem gains `kind`

apps/web/src/components/ai/
  voice-recorder.tsx                     NEW — useVoiceRecorder() hook wrapping MediaRecorder
  ai-draft-banner.tsx                    NEW — review banner shown once per AI-drafted quote

apps/web/src/components/proposals/
  write-scope-panel.tsx                 NEW — trade/summary/tone -> generated scope text
  create-proposal-form.tsx              EDIT — "Write Scope" action wired in

apps/web/src/app/(app)/quotes/
  new-ai/page.tsx                        NEW — customer picker + Type/Record tabs + submit
  page.tsx                               EDIT — "New Quote" becomes a two-option split
  [id]/page.tsx                          EDIT — AI-draft banner + unmatched-line badges on ?from=ai

TASKS.md                                 EDIT — check T201b, refresh rollup
tracking/PROGRESS-TRACKER.csv           EDIT — T201b row -> DONE
```

---

### Task 1: `apiFetch` supports a `FormData` body

**Files:**
- Modify: `apps/web/src/lib/api-client.ts`
- Modify: `apps/web/src/lib/api-client.test.ts`

**Interfaces:**
- Produces: `apiFetch<T>(path, { method?, token?, body? })` — `body` may now be a `FormData`
  instance in addition to any JSON-serializable value

`voice-to-quote` needs `multipart/form-data`, which requires the browser to set its own
`content-type` header (including the multipart boundary) and requires the body to be passed through
unserialized. `apiFetch` currently always sets `content-type: application/json` and always
`JSON.stringify`s the body — this task is the one, minimal, backward-compatible change needed before
anything else in this plan can talk to `voice-to-quote`.

- [ ] **Step 1: Write the failing test**

Add to `apps/web/src/lib/api-client.test.ts` (existing file — add this inside/after the existing
`describe("apiFetch", ...)` block, using the file's established `mockFetchOnce` helper):

```typescript
  it("sends a FormData body unserialized, with no content-type header set", async () => {
    mockFetchOnce(200, { ok: true });
    const form = new FormData();
    form.append("audio", new Blob(["fake-audio-bytes"]), "recording.webm");
    form.append("customer_id", "11111111-1111-1111-1111-111111111111");

    await apiFetch("/v1/ai/voice-to-quote", { method: "POST", body: form, token: "tok" });

    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[1]?.body).toBe(form);
    const headers = call[1]?.headers as Record<string, string>;
    expect(headers["content-type"]).toBeUndefined();
    expect(headers.authorization).toBe("Bearer tok");
  });

  it("still JSON-serializes and sets content-type for a plain object body", async () => {
    mockFetchOnce(200, { ok: true });
    await apiFetch("/v1/things", { method: "POST", body: { name: "widget" } });
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[1]?.body).toBe(JSON.stringify({ name: "widget" }));
    const headers = call[1]?.headers as Record<string, string>;
    expect(headers["content-type"]).toBe("application/json");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- api-client.test.ts`
Expected: `FAIL` — the FormData test fails because `apiFetch` currently always sets
`content-type: application/json` and always calls `JSON.stringify(options.body)`, which would throw
or produce `"{}"` for a `FormData` value (the second test passes already, since that's today's
behavior — it's included so this task can't accidentally break it)

- [ ] **Step 3: Update `apiFetch`**

Replace the body of `apps/web/src/lib/api-client.ts`:

```typescript
import { config } from "@/config";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: string;
}

const REQUEST_TIMEOUT_MS = 10_000;

/**
 * Thin fetch wrapper around the API Gateway. Attaches the bearer token when
 * provided; the gateway verifies it and forwards tenant/user headers to services.
 *
 * A hard timeout guarantees this always settles — some network stacks
 * (proxies, certain sandboxed/automated browser contexts) can leave a fetch
 * neither resolving nor rejecting when a target is unreachable, which would
 * otherwise leave a page's loading state stuck forever with no feedback.
 *
 * A FormData body (multipart uploads, e.g. voice-to-quote) is passed through
 * unserialized with no content-type header — the browser sets that itself,
 * including the multipart boundary, which we cannot replicate by hand.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {};
  if (!isFormData) headers["content-type"] = "application/json";
  if (options.token) headers.authorization = `Bearer ${options.token}`;

  let res: Response;
  try {
    res = await fetch(`${config.apiUrl}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: isFormData
        ? (options.body as FormData)
        : options.body
          ? JSON.stringify(options.body)
          : undefined,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiError(0, "Request timed out — is the API Gateway running?");
    }
    throw new ApiError(0, "Network error — is the API Gateway running?");
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const message =
      (data && (data.message || data.error)) || `Request failed with status ${res.status}`;
    throw new ApiError(res.status, message);
  }
  return data as T;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- api-client.test.ts`
Expected: all tests pass, including the 2 new ones

- [ ] **Step 5: Run the full web suite to check for regressions**

Run: `cd apps/web && pnpm test`
Expected: every pre-existing test still passes — this change only adds a conditional branch, no
existing JSON-body call site changes behavior

- [ ] **Step 6: Typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: clean

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/api-client.ts apps/web/src/lib/api-client.test.ts
git commit -m "feat(T201b): support FormData bodies in apiFetch for voice upload"
```

---

### Task 2: `ai.ts` data layer + `Quote.line_items[].kind`

**Files:**
- Create: `apps/web/src/lib/ai.ts`
- Create: `apps/web/src/lib/ai.test.ts`
- Modify: `apps/web/src/lib/quotes.ts`

**Interfaces:**
- Consumes: `apiFetch` (Task 1), `ApiError` (existing), `Quote`/`LineItem` (this task edits
  `LineItem`)
- Produces: `Trade`, `TRADES`, `TaskCategory`, `ExtractedTask`, `QuoteDraft`, `TextToQuoteInput`,
  `submitTextToQuote(token, input)`, `VoiceToQuoteInput`, `submitVoiceToQuote(token, input)`,
  `ScopeTaskInput`, `ScopeWriterInput`, `ScopeWriterResult`, `generateScopeText(token, input)`,
  `lineItemKindToTaskCategory(kind)`, `quoteLineItemsToScopeTasks(quote)`,
  `describeAiSubmitError(err)`, `isUnmatchedTask(task)`

- [ ] **Step 1: Add `kind` to `LineItem`**

In `apps/web/src/lib/quotes.ts`, replace the `LineItem` interface:

```typescript
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
```

(This mirrors `services/quote-service/app/domain/models.py`'s `ItemKind` enum exactly — the backend
already returns this field; the web type simply never included it before now.)

- [ ] **Step 2: Write the failing tests**

```typescript
// apps/web/src/lib/ai.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import {
  describeAiSubmitError,
  generateScopeText,
  isUnmatchedTask,
  lineItemKindToTaskCategory,
  quoteLineItemsToScopeTasks,
  submitTextToQuote,
  submitVoiceToQuote,
  type ExtractedTask,
} from "@/lib/ai";
import type { Quote } from "@/lib/quotes";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(body),
    }),
  );
}

const SAMPLE_DRAFT = {
  quote_id: "22222222-2222-2222-2222-222222222222",
  trade: "electrical",
  summary: "Panel upgrade and lighting",
  notes: "",
  tasks: [],
  unmatched_count: 0,
  model_id: "claude-opus-5",
  tokens_used: 1200,
  input_kind: "text",
  transcript: null,
  language: null,
};

describe("submitTextToQuote", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to /v1/ai/text-to-quote", async () => {
    mockFetchOnce(201, SAMPLE_DRAFT);
    const result = await submitTextToQuote("tok", {
      text: "Replace the panel with a 200 amp.",
      customer_id: "11111111-1111-1111-1111-111111111111",
    });
    expect(result.quote_id).toBe(SAMPLE_DRAFT.quote_id);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/ai/text-to-quote");
    expect(call[1]?.method).toBe("POST");
  });
});

describe("submitVoiceToQuote", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts multipart form data to /v1/ai/voice-to-quote", async () => {
    mockFetchOnce(201, { ...SAMPLE_DRAFT, input_kind: "voice" });
    const audioBlob = new Blob(["fake-audio"], { type: "audio/webm" });
    await submitVoiceToQuote("tok", {
      audioBlob,
      customer_id: "11111111-1111-1111-1111-111111111111",
    });
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/ai/voice-to-quote");
    expect(call[1]?.body).toBeInstanceOf(FormData);
    const form = call[1]?.body as FormData;
    expect(form.get("customer_id")).toBe("11111111-1111-1111-1111-111111111111");
    expect(form.get("audio")).toBeInstanceOf(Blob);
  });
});

describe("generateScopeText", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to /v1/ai/scope-writer", async () => {
    mockFetchOnce(200, { scope_text: "We will...", model_id: "claude-sonnet-5", tokens_used: 300 });
    const result = await generateScopeText("tok", {
      trade: "electrical",
      summary: "Panel upgrade",
      tasks: [{ description: "Panel", category: "material", item_name: "Panel", quantity: 1, unit: "each" }],
      tone: "professional",
    });
    expect(result.scope_text).toBe("We will...");
  });
});

describe("lineItemKindToTaskCategory", () => {
  it("maps labor and equipment directly", () => {
    expect(lineItemKindToTaskCategory("labor")).toBe("labor");
    expect(lineItemKindToTaskCategory("equipment")).toBe("equipment");
  });

  it("falls back to material for consumable/rental/package", () => {
    expect(lineItemKindToTaskCategory("consumable")).toBe("material");
    expect(lineItemKindToTaskCategory("rental")).toBe("material");
    expect(lineItemKindToTaskCategory("package")).toBe("material");
    expect(lineItemKindToTaskCategory("material")).toBe("material");
  });
});

describe("quoteLineItemsToScopeTasks", () => {
  it("maps a quote's line items into ScopeTaskInput shape", () => {
    const quote = {
      line_items: [
        {
          id: "l1",
          kind: "labor",
          description: "Install panel",
          quantity: 2,
          unit: "hour",
          unit_cost_minor: 0,
          markup_bps: 0,
          unit_price_minor: 0,
          line_total_minor: 0,
          is_optional: false,
          sort_order: 0,
        },
      ],
    } as Quote;
    const tasks = quoteLineItemsToScopeTasks(quote);
    expect(tasks).toEqual([
      { description: "Install panel", category: "labor", item_name: "Install panel", quantity: 2, unit: "hour" },
    ]);
  });
});

describe("describeAiSubmitError", () => {
  it("maps known statuses to specific messages", () => {
    expect(describeAiSubmitError(new ApiError(413, "x"))).toContain("too long");
    expect(describeAiSubmitError(new ApiError(400, "x"))).toContain("format");
    expect(describeAiSubmitError(new ApiError(429, "x"))).toContain("usage limit");
    expect(describeAiSubmitError(new ApiError(502, "x"))).toContain("temporarily unavailable");
    expect(describeAiSubmitError(new ApiError(422, "x"))).toContain("more detail");
  });

  it("falls back to the error message for an unmapped status", () => {
    expect(describeAiSubmitError(new ApiError(500, "boom"))).toBe("boom");
  });

  it("falls back to a generic message for a non-ApiError", () => {
    expect(describeAiSubmitError(new Error("network down"))).toBe(
      "Something went wrong. Please try again.",
    );
  });
});

describe("isUnmatchedTask", () => {
  it("is true when pricebook_item_id is null", () => {
    const task = { pricebook_item_id: null } as ExtractedTask;
    expect(isUnmatchedTask(task)).toBe(true);
  });

  it("is false when pricebook_item_id is set", () => {
    const task = { pricebook_item_id: "pb-1" } as ExtractedTask;
    expect(isUnmatchedTask(task)).toBe(false);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- ai.test.ts`
Expected: `FAIL` — cannot find module `@/lib/ai`

- [ ] **Step 4: Implement `ai.ts`**

```typescript
// apps/web/src/lib/ai.ts
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- ai.test.ts`
Expected: `13 passed`

- [ ] **Step 6: Run the full web suite and typecheck**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: all pass, zero type errors (the `kind` addition to `LineItem` is additive — no existing
code destructures `LineItem` exhaustively, so nothing should break; if `pnpm typecheck` surfaces an
unrelated call site that constructs a `LineItem`-shaped object without `kind`, add `kind: "material"`
there rather than making the field optional, since the backend always sends it)

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/ai.ts apps/web/src/lib/ai.test.ts apps/web/src/lib/quotes.ts
git commit -m "feat(T201b): add ai-service data layer (text/voice/scope-writer + pure helpers)"
```

---

### Task 3: `useVoiceRecorder` hook

**Files:**
- Create: `apps/web/src/components/ai/voice-recorder.tsx`

**Interfaces:**
- Consumes: nothing new (browser `MediaRecorder`/`navigator.mediaDevices` APIs only)
- Produces: `RecorderState = "idle" | "requesting" | "recording" | "recorded" | "denied"`,
  `useVoiceRecorder(): { state, audioBlob, start, stop, reset }`

This task has no unit tests — `MediaRecorder`/`getUserMedia` are browser APIs with no meaningful
fake in a Node/jsdom-less Vitest environment (this repo's Vitest runs with `environment: "node"`).
Verification is `pnpm typecheck` + `pnpm build`, plus the live browser pass in Task 7.

- [ ] **Step 1: Implement the hook**

```tsx
// apps/web/src/components/ai/voice-recorder.tsx
"use client";

import * as React from "react";

export type RecorderState = "idle" | "requesting" | "recording" | "recorded" | "denied";

export interface UseVoiceRecorder {
  state: RecorderState;
  audioBlob: Blob | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

/**
 * Wraps the browser's native MediaRecorder — no new dependency (M15 web UI
 * spec D3). Both mime types MediaRecorder actually produces (audio/webm on
 * Chrome/Firefox, audio/mp4 on Safari) are already on the backend's
 * SUPPORTED_AUDIO_MIME_TYPES whitelist, verified against the source.
 *
 * Stops every MediaStream track on unmount so a page navigation mid-recording
 * never leaves the microphone hot.
 */
export function useVoiceRecorder(): UseVoiceRecorder {
  const [state, setState] = React.useState<RecorderState>("idle");
  const [audioBlob, setAudioBlob] = React.useState<Blob | null>(null);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);

  const stopTracks = React.useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  React.useEffect(() => stopTracks, [stopTracks]);

  const start = React.useCallback(async () => {
    setState("requesting");
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        setAudioBlob(new Blob(chunksRef.current, { type: recorder.mimeType }));
        setState("recorded");
        stopTracks();
      };
      recorder.start();
      setState("recording");
    } catch {
      setState("denied");
    }
  }, [stopTracks]);

  const stop = React.useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const reset = React.useCallback(() => {
    setAudioBlob(null);
    setState("idle");
  }, []);

  return { state, audioBlob, start, stop, reset };
}
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: clean

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/ai/voice-recorder.tsx
git commit -m "feat(T201b): add useVoiceRecorder hook (native MediaRecorder wrapper)"
```

---

### Task 4: `/quotes/new-ai` entry point + `/quotes` split control

**Files:**
- Create: `apps/web/src/app/(app)/quotes/new-ai/page.tsx`
- Modify: `apps/web/src/app/(app)/quotes/page.tsx`

**Interfaces:**
- Consumes: `useVoiceRecorder` (Task 3), `submitTextToQuote`/`submitVoiceToQuote`/
  `describeAiSubmitError`/`QuoteDraft` (Task 2), `listCustomers` (existing), `useAuthGuard`
  (existing)

No unit tests for this task (page-level UI, no component-test infra) — verified by typecheck +
build, plus Task 7's live browser pass.

- [ ] **Step 1: Update `/quotes`'s "New Quote" control**

In `apps/web/src/app/(app)/quotes/page.tsx`, replace:

```tsx
        <Link href="/quotes/new" className={buttonVariants({ variant: "default" })}>
          New Quote
        </Link>
```

with:

```tsx
        <div className="flex gap-2">
          <Link href="/quotes/new" className={buttonVariants({ variant: "outline" })}>
            Build Manually
          </Link>
          <Link href="/quotes/new-ai" className={buttonVariants({ variant: "default" })}>
            Describe the Job
          </Link>
        </div>
```

- [ ] **Step 2: Create the entry-point page**

```tsx
// apps/web/src/app/(app)/quotes/new-ai/page.tsx
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
import { describeAiSubmitError, submitTextToQuote, submitVoiceToQuote, type QuoteDraft } from "@/lib/ai";
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
                <p className="text-sm text-destructive">
                  Microphone access was denied. Allow microphone access in your browser to record,
                  or use the Type tab instead.
                </p>
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
```

- [ ] **Step 3: Typecheck and build**

Run: `cd apps/web && pnpm typecheck && pnpm build`
Expected: zero type errors; `next build` produces `/quotes/new-ai` with zero errors

- [ ] **Step 4: Commit**

```bash
git add "apps/web/src/app/(app)/quotes/new-ai/page.tsx" "apps/web/src/app/(app)/quotes/page.tsx"
git commit -m "feat(T201b): add /quotes/new-ai entry point (text/voice job description)"
```

---

### Task 5: AI-draft review banner on the quote detail page

**Files:**
- Create: `apps/web/src/components/ai/ai-draft-banner.tsx`
- Modify: `apps/web/src/app/(app)/quotes/[id]/page.tsx`

**Interfaces:**
- Consumes: `QuoteDraft`, `isUnmatchedTask` (Task 2)

No unit tests (page/component-level UI) — typecheck + build + Task 7's live pass.

- [ ] **Step 1: Create the banner component**

```tsx
// apps/web/src/components/ai/ai-draft-banner.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { QuoteDraft } from "@/lib/ai";

interface AiDraftBannerProps {
  draft: QuoteDraft;
}

/**
 * Shown once, immediately after an AI-drafted quote is created — reads the
 * extraction result the create call returned (M15 web UI spec §4.2). Nothing
 * has been sent to the customer yet; this is purely a review aid.
 */
export function AiDraftBanner({ draft }: AiDraftBannerProps) {
  return (
    <Card className="border-primary/40 bg-primary/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          AI-drafted quote
          <Badge variant="secondary" className="capitalize">
            {draft.trade}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-muted-foreground">Review before sending — nothing has been sent yet.</p>
        <p>{draft.summary}</p>
        {draft.notes && <p className="text-muted-foreground">{draft.notes}</p>}
        {draft.transcript && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">Transcript: </span>
            {draft.transcript}
          </p>
        )}
        {draft.unmatched_count > 0 && (
          <p className="font-medium text-destructive">
            {draft.unmatched_count} line{draft.unmatched_count === 1 ? "" : "s"} need pricing —
            flagged below.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Wire it into the quote detail page**

Replace the full contents of `apps/web/src/app/(app)/quotes/[id]/page.tsx`:

```tsx
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { acceptQuote, getQuote, rejectQuote, sendQuote, statusBadgeVariant } from "@/lib/quotes";
import { formatMoney } from "@/lib/money";
import { ApiError } from "@/lib/api-client";
import { isUnmatchedTask, type QuoteDraft } from "@/lib/ai";
import { AiDraftBanner } from "@/components/ai/ai-draft-banner";

const AI_DRAFT_STORAGE_PREFIX = "ai-draft:";

export default function QuoteDetailPage() {
  const token = useAuthGuard();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [aiDraft, setAiDraft] = React.useState<QuoteDraft | null>(null);

  React.useEffect(() => {
    if (searchParams.get("from") !== "ai") return;
    const key = `${AI_DRAFT_STORAGE_PREFIX}${params.id}`;
    const raw = sessionStorage.getItem(key);
    if (!raw) return;
    sessionStorage.removeItem(key);
    try {
      setAiDraft(JSON.parse(raw) as QuoteDraft);
    } catch {
      // Malformed/stale sessionStorage entry — ignore; the plain quote page still renders fine.
    }
  }, [params.id, searchParams]);

  const {
    data: quote,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["quotes", params.id],
    queryFn: () => getQuote(token as string, params.id),
    enabled: !!token,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["quotes", params.id] });
    queryClient.invalidateQueries({ queryKey: ["quotes"] });
  }

  const sendMutation = useMutation({
    mutationFn: () => sendQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to send."),
  });
  const acceptMutation = useMutation({
    mutationFn: () => acceptQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to accept."),
  });
  const rejectMutation = useMutation({
    mutationFn: () => rejectQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to reject."),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading quote…</p>;
  if (isError || !quote) return <p className="text-sm text-destructive">Quote not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{quote.number}</h1>
            <Badge variant={statusBadgeVariant(quote.status)} className="capitalize">
              {quote.status}
            </Badge>
          </div>
          <p className="text-muted-foreground">{quote.title ?? "Untitled quote"}</p>
        </div>
        <div className="flex gap-2">
          {(quote.status === "draft" ||
            quote.status === "sent" ||
            quote.status === "viewed" ||
            quote.status === "accepted") && (
            <Link
              href={`/proposals/new?quote_id=${quote.id}`}
              className={buttonVariants({ variant: "outline" })}
            >
              Create Proposal
            </Link>
          )}
          {quote.status === "draft" && (
            <Button onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
              {sendMutation.isPending ? "Sending…" : "Send"}
            </Button>
          )}
          {(quote.status === "sent" || quote.status === "viewed") && (
            <>
              <Button
                variant="outline"
                onClick={() => rejectMutation.mutate()}
                disabled={rejectMutation.isPending}
              >
                Mark Rejected
              </Button>
              <Button onClick={() => acceptMutation.mutate()} disabled={acceptMutation.isPending}>
                Mark Accepted
              </Button>
            </>
          )}
        </div>
      </div>

      {aiDraft && <AiDraftBanner draft={aiDraft} />}

      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Line Items</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Description</th>
                  <th className="py-2 pr-4 text-right font-medium">Qty</th>
                  <th className="py-2 pr-4 font-medium">Unit</th>
                  <th className="py-2 pr-4 text-right font-medium">Unit Price</th>
                  <th className="py-2 pr-4 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {quote.line_items.map((item, index) => {
                  const task = aiDraft?.tasks[index];
                  const flagUnmatched = task ? isUnmatchedTask(task) : false;
                  return (
                    <tr key={item.id} className="border-b last:border-0">
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          {item.description}
                          {flagUnmatched && (
                            <Badge variant="destructive" className="whitespace-nowrap">
                              Unmatched — needs pricing
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-right">{item.quantity}</td>
                      <td className="py-3 pr-4">{item.unit}</td>
                      <td className="py-3 pr-4 text-right">
                        {formatMoney(item.unit_price_minor, quote.currency)}
                      </td>
                      <td className="py-3 pr-4 text-right font-medium">
                        {formatMoney(item.line_total_minor, quote.currency)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex justify-end">
            <div className="w-56 space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>{formatMoney(quote.subtotal_minor, quote.currency)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tax</span>
                <span>{formatMoney(quote.tax_minor, quote.currency)}</span>
              </div>
              <div className="flex justify-between border-t pt-1 text-base font-semibold">
                <span>Total</span>
                <span>{formatMoney(quote.total_minor, quote.currency)}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Typecheck and build**

Run: `cd apps/web && pnpm typecheck && pnpm build`
Expected: zero type errors; `next build` produces `/quotes/[id]` with zero errors. Note:
`useSearchParams()` without a `<Suspense>` boundary is a pattern already present elsewhere in this
app (`apps/web/src/app/(app)/proposals/new/page.tsx`, flagged as a non-blocking Minor in an earlier
feature's final review) — this task follows that same existing precedent rather than introducing a
new one; do not add a `<Suspense>` boundary here unless the build actually fails without it.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/ai/ai-draft-banner.tsx "apps/web/src/app/(app)/quotes/[id]/page.tsx"
git commit -m "feat(T201b): show AI-draft review banner + unmatched-line badges"
```

---

### Task 6: "Write Scope" action on the proposal editor

**Files:**
- Create: `apps/web/src/components/proposals/write-scope-panel.tsx`
- Modify: `apps/web/src/components/proposals/create-proposal-form.tsx`

**Interfaces:**
- Consumes: `generateScopeText`, `quoteLineItemsToScopeTasks`, `TRADES`, `Trade` (Task 2);
  `setValue` (already destructured in `create-proposal-form.tsx`'s existing `useForm()` call)

No unit tests (component-level UI) — typecheck + build + Task 7's live pass.

- [ ] **Step 1: Create the panel component**

```tsx
// apps/web/src/components/proposals/write-scope-panel.tsx
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
```

- [ ] **Step 2: Wire it into `create-proposal-form.tsx`**

Add this import near the top of `apps/web/src/components/proposals/create-proposal-form.tsx`,
alongside the existing `import { Button } from "@/components/ui/button";` line:

```tsx
import { WriteScopePanel } from "@/components/proposals/write-scope-panel";
```

Add one line of new state inside the `CreateProposalForm` component, alongside the existing
`const [serverError, setServerError] = React.useState<string | null>(null);`:

```tsx
  const [writeScopeOpen, setWriteScopeOpen] = React.useState(false);
```

Replace the existing scope-of-work field block:

```tsx
          <div className="space-y-2">
            <Label htmlFor="scopeOfWork">Scope of work</Label>
            <textarea
              id="scopeOfWork"
              rows={6}
              className={textareaClassName}
              {...register("scopeOfWork")}
            />
            {errors.scopeOfWork && (
              <p className="text-sm text-destructive">{errors.scopeOfWork.message}</p>
            )}
          </div>
```

with:

```tsx
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="scopeOfWork">Scope of work</Label>
              {!writeScopeOpen && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setWriteScopeOpen(true)}
                >
                  Write Scope
                </Button>
              )}
            </div>
            {writeScopeOpen && (
              <WriteScopePanel
                token={token}
                quote={quote}
                onGenerated={(text) => setValue("scopeOfWork", text, { shouldValidate: true })}
                onClose={() => setWriteScopeOpen(false)}
              />
            )}
            <textarea
              id="scopeOfWork"
              rows={6}
              className={textareaClassName}
              {...register("scopeOfWork")}
            />
            {errors.scopeOfWork && (
              <p className="text-sm text-destructive">{errors.scopeOfWork.message}</p>
            )}
          </div>
```

(`setValue` is already destructured from this component's existing `useForm()` call — no change
needed there.)

- [ ] **Step 3: Typecheck and build**

Run: `cd apps/web && pnpm typecheck && pnpm build`
Expected: zero type errors; `next build` clean

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/proposals/write-scope-panel.tsx apps/web/src/components/proposals/create-proposal-form.tsx
git commit -m "feat(T201b): add Write Scope action to the proposal editor"
```

---

### Task 7: Full gate, live verification, tracker bookkeeping

**Files:**
- Modify: `TASKS.md`
- Modify: `tracking/PROGRESS-TRACKER.csv`

- [ ] **Step 1: Run every gate**

```bash
cd "/d/TradeQuote AI/apps/web" && pnpm typecheck && pnpm test && pnpm build
```

Expected: all clean. Record the actual test count and route list — you will cite them in the
tracker text. If anything fails, STOP and report BLOCKED; do not edit tracker files to describe a
green state that does not exist.

- [ ] **Step 2: Live browser verification**

Start the API Gateway, `ai-service`, `quote-service`, `customer-service`, `proposal-service`, and the
web app. Confirm:

- `/quotes` shows the two-option split control; both links navigate correctly
- `/quotes/new-ai`: pick a customer, type a description ≥10 chars, submit — redirects to
  `/quotes/{id}?from=ai` showing the AI-draft banner (trade, summary, unmatched count if any) and
  any unmatched lines flagged in the line-items table
- Record tab: click Start Recording, grant mic permission, speak, Stop Recording, submit — same
  review flow. Denying mic permission shows the denied-state message, not a stuck spinner
- Refreshing the quote detail page after the above makes the banner disappear (sessionStorage
  consumed) while the quote's own line items remain exactly as before
- On an existing quote's proposal editor, click "Write Scope", pick a trade, enter a summary,
  Generate — the scope-of-work field is replaced with generated prose and remains editable
- A quote's detail page not reached via `?from=ai` shows no banner and no badges — zero visible
  change from before this feature

If Postgres/the full stack is unavailable in this environment (as has been the case for prior
features in this project), record that explicitly rather than skipping the note — this feature adds
no new backend surface of its own, but every flow above still requires the already-existing backend
services to be reachable to prove out live.

- [ ] **Step 3: Update `TASKS.md`**

Re-read the file first — do not assume line numbers are still current. Find the current `T201b`
line and:

- Change `- [ ]` to `- [x]`
- Replace the trailing text with a completed summary: what shipped (entry point, review banner,
  Write Scope action), the measured test count from Step 1, that this required a small, additive
  `apiFetch` extension (FormData support) as the one shared-infra touch, and a link to both
  [docs/modules/M15-ai-quote-assistant-web-ui.md](docs/modules/M15-ai-quote-assistant-web-ui.md)
  (spec) and
  [docs/modules/M15-ai-quote-assistant-web-ui-plan.md](docs/modules/M15-ai-quote-assistant-web-ui-plan.md)
  (plan)
- Remove `T201b` from the "Check for Next Task" ready table
- Recompute the Module Completion Rollup table's Phase 2 done count/percentage and the Total row
  from the actual current checkbox state — do not copy stale numbers from this plan

- [ ] **Step 4: Update `tracking/PROGRESS-TRACKER.csv`**

Re-read the live `T201b` row. Change `NOT_STARTED`/blank status to `DONE`, fill Start Date and End
Date with the actual date, and write a Notes cell describing the finished work with your measured
test count, following the exact quoting/format convention already used by other rows in this file.

- [ ] **Step 5: Commit**

```bash
git add TASKS.md tracking/PROGRESS-TRACKER.csv
git commit -m "docs(T201b): mark M15 AI Quote Assistant web UI done, refresh rollup and tracker"
```

- [ ] **Step 6: Note for Agent 1 sign-off**

Per `AGENTS.md`'s cross-agent audit rule, flag this branch for CTO review before merge. Nothing here
touches another agent's module or a shared package, so the review surface is narrow: the `apiFetch`
FormData extension (Task 1, the one shared-infra change) and the multipart upload path end-to-end
are the two things worth a second look.

---

## Self-Review Notes

**Spec coverage:** D1 (review on the created draft) → Tasks 4–5 (redirect + banner + badges, no
preview endpoint added). D2 (`/quotes/new-ai` parallel page) → Task 4. D3 (native `MediaRecorder`,
verified mime whitelist) → Task 3. D4 (asked trade, never guessed) → Task 6's `WriteScopePanel`. D5
(disable-on-click, no auto-retry) → every `useMutation` in Tasks 4/6 has no `retry` override,
inheriting the library default; submit buttons disable via `mutation.isPending` throughout. D6
(`kind` added to `LineItem`) → Task 2 Step 1. §5 error handling → Task 2's
`describeAiSubmitError` + Task 3's `denied` state + Task 3's unmount track-stopping. §6 testing
strategy → Task 2's unit tests for every pure/API-call function; Tasks 3–6's typecheck+build-only
verification, matching this project's established no-component-test-infra precedent. §8 DoD → Task 7.

**Placeholder scan:** no TBD/TODO; every step has complete code or an exact command with expected
output.

**Type consistency:** `QuoteDraft`, `ExtractedTask`, `Trade`, `TaskCategory` (Task 2) are consumed
unchanged by Task 4 (`onDraftCreated(draft: QuoteDraft)`), Task 5 (`AiDraftBanner`'s prop, `isUnmatchedTask(task: ExtractedTask)`), and Task 6 (`WriteScopePanel`'s `Trade` state). `LineItem["kind"]`
(Task 2 Step 1) is the exact type `lineItemKindToTaskCategory` (Task 2 Step 4) accepts.
`quoteLineItemsToScopeTasks(quote: Quote)` (Task 2) is called identically in Task 6's
`WriteScopePanel`. `submitTextToQuote`/`submitVoiceToQuote`/`generateScopeText` signatures match
their Task 2 definitions everywhere they're called in Tasks 4 and 6.
