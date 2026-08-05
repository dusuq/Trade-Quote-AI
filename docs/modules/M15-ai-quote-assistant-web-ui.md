# T201b — M15 AI Quote Assistant Web UI · Design Spec

| Field            | Value                                                             |
| ---------------- | ----------------------------------------------------------------- |
| **Task**         | `T201b`                                                           |
| **Module**       | M15 — AI Quote Assistant (web UI)                                 |
| **Owner agent**  | Agent 2 (Sonnet 5)                                                |
| **Phase**        | Phase 2 — AI + Delivery                                           |
| **Dependencies** | `T201` AI Quote Assistant backend ✅ (CTO-signed-off, 2026-07-30) |
| **Date**         | 2026-07-28                                                        |
| **Status**       | Design approved — ready for implementation planning               |
| **Bounded ctx**  | `apps/web` only — no backend changes                              |

---

## 1. Problem

`services/ai-service` (T201/T202) is complete, tested (185/185), and CTO-signed-off, but nothing in
the web app calls it. A contractor cannot record or type a job description, cannot see an
AI-generated quote draft, and the proposal editor's "Scope of Work" field has no way to generate
prose from structured data. T201's own spec recorded this explicitly as gap D8/§6.1, tracked as
`T201b`.

## 2. Decisions

### D1 — Review happens on the created draft, not before creation

`POST /v1/ai/text-to-quote` and `/voice-to-quote` create the quote as part of the call (`201`, real
`quote_id`, status `draft`) — there is no extract-only preview endpoint, and adding one would reopen
a service Agent 1 already built, tested, and got signed off, well beyond "web UI" scope.

**Rejected alternative:** add a new `POST /v1/ai/text-to-quote/preview` endpoint that runs extraction
without creating anything, so the web app can show a true pre-creation review step matching the
task line's literal wording. Rejected because it requires reopening and re-testing a signed-off
service and duplicates match-scoring logic the real endpoint already exercises, for a benefit
(avoiding one throwaway draft row) that doesn't justify the cross-agent coordination cost.

**Why D1 wins:** a draft quote is already safe by construction — nothing is sent to a customer or
committed until the contractor acts further. The review surface is simply the quote detail page,
banner-annotated to show what the AI extracted and which lines still need pricing, using the
line-item editing T108/T109 already built. Zero backend changes.

### D2 — New `/quotes/new-ai` page, parallel to the existing manual form

**Rejected alternative:** an inline collapsible panel on the existing `/quotes/new` form. Rejected
because it couples two different interaction models (a structured multi-field form vs. a single
text/voice input that redirects elsewhere on submit) into one component, risking collateral changes
to an already-shipped, tested flow for a feature that behaves nothing like it.

**Why D2 wins:** the manual flow stays completely untouched — zero regression risk — and the AI flow
gets room for its own loading/transcript/error states without cramming them into the existing form's
layout. `/quotes`'s "New Quote" control becomes a two-option split (Build manually / Describe the
job).

### D3 — Native `MediaRecorder`, no new dependency

**Rejected alternative:** a recording library (e.g. RecordRTC) to smooth cross-browser quirks.
Rejected because this app has zero client-side media dependencies today, and the native API's
rougher edges are a browser-compatibility concern for the target audience (modern
Chrome/Safari/Edge), not a blocking one.

**Verified, not assumed:** the two mime types `MediaRecorder` actually produces are both already on
the backend's whitelist (`app/application/audio.py`'s `SUPPORTED_AUDIO_MIME_TYPES`) —
`audio/webm` (Chrome/Firefox's default) and `audio/mp4` (Safari's default) — with
`normalize_mime_type` already stripping the `;codecs=opus`-style suffix `MediaRecorder` appends
before comparing. Checked directly against the backend source rather than assumed.

### D4 — Scope-writer's `trade` is asked, not guessed

A `Quote` has no stored `trade` field. **Rejected alternative:** silently default to `"general"`.
Rejected because "general" produces visibly genericized prose for what the endpoint's entire value
proposition is — trade-aware phrasing — undermining the feature for the common case of a contractor
who works one specific trade. The "Write Scope" action asks for trade (10-value select) plus a
one-line job summary (prefilled from `quote.title` if present) and tone, alongside the task list
that's derived automatically from the quote's own line items.

### D5 — Disable-on-click, no auto-retry, ever

The M15 spec records a known gap: no idempotency key, so a retried `text/voice-to-quote` call
creates a second draft quote. This app's `QueryClient` only overrides `queries.retry` (to `1`) in
`providers.tsx` — `mutations` are never overridden, so they already inherit TanStack Query's library
default of zero automatic retries. The only additional guard needed is disabling the submit button
the instant it's clicked, re-enabling only on a genuine response (success or error), and never
programmatically retrying a failed submission — the same posture already used by every other mutating
action in this app (T206, T203).

### D6 — `Quote.line_items[].kind` is added to the web's TS type

The backend's `LineItemResponse` already returns `kind: ItemKind`; the web app's `LineItem` interface
in `apps/web/src/lib/quotes.ts` simply never included it. This is a one-line addition that exposes
data already on the wire, needed to map a quote's line items into `ScopeTaskInput[]`'s `category`
field for the scope-writer action.

## 3. File structure

```
apps/web/src/lib/
  ai.ts                                NEW — API client + wire types (mirrors ai-service's schemas.py)
  ai.test.ts                           NEW
  quotes.ts                            EDIT — LineItem gains `kind`

apps/web/src/components/ai/
  voice-recorder.tsx                   NEW — MediaRecorder wrapper: idle → recording → recorded → error
  ai-draft-banner.tsx                  NEW — "AI-drafted, review before sending" summary card

apps/web/src/app/(app)/quotes/
  new-ai/page.tsx                      NEW — customer picker + Type/Record tabs + submit
  page.tsx                             EDIT — "New Quote" becomes a two-option split control
  [id]/page.tsx                        EDIT — reads the one-time sessionStorage handoff on `?from=ai`

apps/web/src/components/proposals/
  create-proposal-form.tsx             EDIT — "Write Scope" action (trade + summary + tone → prose)
```

## 4. Data flow

### 4.1 Text/voice submission

1. `new-ai/page.tsx`: customer picker (reused `listCustomers` pattern) + a two-tab input — **Type**
   (textarea, `min(10)` matching `TextToQuoteRequest.text`) or **Record** (`voice-recorder.tsx`).
2. Submit disables immediately (`useMutation`, inherits zero auto-retry per D5).
3. Text → `POST /v1/ai/text-to-quote` (JSON). Voice → `POST /v1/ai/voice-to-quote`
   (`multipart/form-data` via `FormData` — this app's first binary upload).
4. On `201`: write the full response to `sessionStorage["ai-draft:{quote_id}"]`, then
   `router.push('/quotes/' + quote_id + '?from=ai')`.
5. On error, map by status: `413` → "recording too long"; `400` → "unsupported audio format"; `429`
   → "AI usage limit reached today"; `502` → "the AI service is temporarily unavailable"; `422` →
   "couldn't make sense of that description — try adding more detail"; anything else → generic
   fallback. Button re-enables; entered text/recording is preserved, never cleared.

### 4.2 Review banner

On mount, `[id]/page.tsx` checks `sessionStorage["ai-draft:{id}"]` when the URL has `?from=ai`. If
present: parse it, render `AiDraftBanner` (trade, summary, notes, unmatched count, transcript if
voice), then delete the key — a refresh shows the plain quote page, which is correct: the quote's
own line items (editable via the existing T108/T109 UI) are the durable record, not this banner.

`tasks[]` in the response is order-matched to the quote's `line_items[]` (both produced by the same
creation call, in the same order) to flag which rendered rows are unmatched: a small "Unmatched —
needs pricing" badge on any row where `unit_cost_minor === 0` and the corresponding task had no
`pricebook_item_id`. Read-only visual layer on the _existing_ table — no change to how it edits or
submits.

### 4.3 Scope-writer

1. "Write Scope" button on `create-proposal-form.tsx` opens an inline panel: Trade (select, all 10
   `Trade` values), Job summary (short text, prefilled from `quote.title` if present), Tone (select:
   professional/friendly/formal).
2. On Generate: map `quote.line_items[]` → `ScopeTaskInput[]` — `category` from `kind`, with
   `RENTAL`/`PACKAGE`/`CONSUMABLE` falling back to `MATERIAL` (the closest of the three
   `TaskCategory` values; a named, deliberate lossy mapping, not a silent guess).
3. `POST /v1/ai/scope-writer` → `scope_text` replaces the `scopeOfWork` field's current value, still
   user-editable afterward — same pattern T203 already established for terms/warranty prefills.

## 5. Error handling & edge cases

| Condition                                                                   | Behavior                                                                                          |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Mic permission denied                                                       | Own state in `voice-recorder.tsx` (`idle→requesting→denied`), separate from the submit-error path |
| Recording stopped with 0 captured audio                                     | Submit disabled until `chunks.length > 0`                                                         |
| User navigates away mid-recording                                           | Stop all `MediaStream` tracks on unmount — never leave the mic hot                                |
| Quote detail page visited directly (no `?from=ai`, or key already consumed) | Renders exactly as today — zero behavior change for any non-AI quote                              |
| Zero unmatched lines                                                        | No badges render; banner still shows (summary/notes are still useful)                             |

## 6. Testing strategy

- `ai.ts`: unit tests for every API-call function (mirroring this app's established `vitest` +
  mocked-`fetch` pattern) plus pure helpers — status→message mapping, task↔line-item unmatched
  matching, and the `ScopeTaskInput` category mapping including the lossy-fallback cases.
- `voice-recorder.tsx` and the page-level components: **no unit tests** — this repo has no
  component-test infrastructure (established during T206/T203). Verification is `pnpm typecheck` +
  `pnpm build`, the same bar every prior UI task in this project used.
- Live browser verification: submit text → review banner + unmatched badges render correctly;
  record → submit → same; Write Scope → prose lands in the field and stays editable; direct
  navigation to an existing quote shows no banner.

## 7. Out of scope (deferred, not forgotten)

- An extract-only preview endpoint (D1) — would require backend changes outside this task.
- Idempotency / dedupe (M15's own known gap #3) — a UI-side guard (D5) is the mitigation available
  without backend work; the underlying gap remains tracked against T201.
- `created_via` provenance for typed input (M15 known gap #2) — needs `packages/types` +
  quote-service changes together with Agent 1; not a web-UI-only change.
- Editing/regenerating a scope-writer result beyond simple textarea edits (e.g. "make it shorter"
  follow-up prompts) — the field is just editable text once generated, same as terms/warranty.

## 8. Definition of Done

- [ ] `/quotes/new-ai` — customer picker, Type/Record tabs, submit with correct error mapping
- [ ] `/quotes` — split "New Quote" control
- [ ] `/quotes/[id]` — AI-draft banner + unmatched-line badges on `?from=ai`, zero change otherwise
- [ ] `create-proposal-form.tsx` — "Write Scope" action
- [ ] `ai.ts` unit tests passing; `pnpm typecheck` / `pnpm test` / `pnpm build` clean
- [ ] Live browser verification of all four flows above
- [ ] `TASKS.md` `T201b` checked; `tracking/PROGRESS-TRACKER.csv` row set to `DONE`
