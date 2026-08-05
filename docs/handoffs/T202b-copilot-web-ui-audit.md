# CTO Audit — T202b (M16 AI Copilot web UI)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-08-01
- **Built by:** Agent 2
- **Verdict:** ✅ **Signed off.** Every claim reproduced, including the two that actually carry
  risk — the cost claim and the write-path claim — and both are true _structurally_, not just by
  convention. The nits the report discloses are genuinely still there, which is the right kind of
  honesty. One defect the report doesn't mention: adding a missing item twice silently creates a
  duplicate line.

## Gates

| Claim                           | Result                                                                |
| ------------------------------- | --------------------------------------------------------------------- |
| Web tests                       | **109 passed** (11 files) — 94 at T202b's time, since raised by T204b |
| `copilot.test.ts` — 9 new tests | **9 tests**, passing                                                  |
| `tsc --noEmit` clean            | clean, exit 0                                                         |
| `next build` clean              | clean, 17 routes                                                      |

Gates were re-run at this HEAD during the T204b sign-off; nothing but docs has changed since.

## The cost claim — true, and true for a structural reason

The report says _"nothing runs automatically since every call is metered."_ On a page a contractor
opens constantly, an auto-firing LLM call would burn the tenant's daily spend cap just by browsing
— so this is the claim worth checking hardest.

It holds, and it holds for the right reason: **all four operations are `useMutation`, never
`useQuery`.** A `useQuery` fires on mount; a mutation cannot fire without an explicit `.mutate()`.
The two metered calls (`analyzePricing`, `findMissingItems`) are each behind their own button, and
`CopilotPanel` — although rendered unconditionally on every quote detail page — costs nothing to
render. That's a structural guarantee rather than a discipline that erodes on the next edit.

Two supporting details are also right. "Analyze Pricing" is disabled when
`quote.line_items.length === 0`, matching T202's empty-quote short-circuit so the client doesn't
even make the call the backend would refuse to spend on. And in `InlineRewriteEditor`, "Rewrite" is
advisory — it only replaces the text in the textarea — while **"Save" is the only action that
writes**, so no AI output is ever auto-applied.

## The write-path claim — true

_"Copilot itself never gets a write path."_ Verified by reading every function in `copilot.ts`:

| Function                                             | Endpoint                                               |
| ---------------------------------------------------- | ------------------------------------------------------ |
| `analyzePricing`, `findMissingItems`, `rewriteTexts` | `POST /v1/ai/copilot/*` (read-only advisory, per T202) |
| `addMissingItemToQuote`                              | `POST /v1/quotes/{id}/line-items`                      |
| `applyMarkupSuggestion`, `updateLineItemDescription` | `PUT /v1/quotes/{id}/line-items/{itemId}`              |

Every mutation goes through quote-service's own existing routes, so quote-service's validation,
tenancy, and money rules apply unchanged. The copilot advises; the quote service remains the sole
writer of quote state. This is the correct shape and it matches T202's read-only backend exactly.

## A cross-service claim I checked because it's easy to get wrong

```ts
/** The three missing-item category values are already valid quote-service
 * ItemKind values — a direct passthrough, not a lossy mapping. */
```

True. `ItemKind` is `material | labor | equipment | consumable | rental | package`
(`services/quote-service/app/domain/models.py:48`), and the copilot's three categories are a strict
subset. The web's `LineItem["kind"]` and `packages/types` list all six identically. A comment
asserting "not a lossy mapping" is the kind of thing that silently becomes false when an enum
grows, so it is worth having verified once — it's correct today.

Consequence worth naming, not a defect: the copilot can only ever suggest 3 of the 6 kinds, so
consumables, rentals, and packages are never proposed. That's T202's LLM schema, not this UI.

## Finding — "Add to Quote" can silently create duplicates

`addMissingItemToQuote` is a **POST**, and after it succeeds:

```tsx
const addMissingMutation = useMutation({
  mutationFn: (item: MissingItem) => addMissingItemToQuote(token, quote.id, item),
  onSuccess: invalidateQuote, // ← nothing else
});
```

`onSuccess` only invalidates the quote. It does not remove the item from `missingResult`, does not
record that the item was added, and the button re-enables the moment the mutation settles
(`disabled={addMissingMutation.isPending}`). So the suggestion sits there looking exactly as it did
before, inviting a second click — which POSTs again and creates a **second $0 line item**.

The contrast with the neighbouring action is what makes this worth fixing rather than shrugging at:
"Apply suggested markup" is a `PUT` with a fixed `markup_bps`, so clicking it twice is idempotent
and harmless. The two buttons look and behave identically to the user, but only one of them is safe
to double-click.

The failure is also quiet. The added line appears in the Line Items table _above_ the panel, so a
contractor who doesn't scroll gets no local confirmation that anything happened — the exact
condition that produces a second click. And because these lines are deliberately added at $0 "for
the contractor to price", a duplicate is easy to miss until the quote total is wrong.

**Fix:** track added items in local state and either remove them from the list or render the button
as a disabled "Added ✓". Tracked as **T202c**.

## Disclosed nits — confirmed present, accurately characterised

The report discloses two Minor nits and declines to fix them, noting they were inherited from the
plan's reference code. Both are real, and "Minor" is fair:

- **Shared pending/error state across rows.** `applyMutation.isPending` disables _every_ "Apply
  suggested markup" button, and `addMissingMutation.isPending` every "Add to Quote". `pricingError`
  is panel-level too, so an error from applying row 3 renders at the top of the section rather than
  next to row 3. Cosmetic at current list sizes.
- **No `<label>` on either textarea** (`copilot-panel.tsx:188`, `inline-rewrite-editor.tsx:58`) —
  both rely on a placeholder or surrounding context. Straightforward a11y gap.

Disclosing known nits instead of quietly leaving them for the auditor to find is the behaviour I
want; recording them here so they're tracked rather than re-discovered. Folded into **T202c**.

## Minor — unchecked array index

`setText(result.rewritten[0])` assumes the response contains exactly one entry. That's guaranteed
by T202's 1:1 text-count enforcement (mismatch → 422, verified in the T202 audit), so this is safe
today — it just depends on a server invariant with no client-side guard. Noting, not tracking.

## Correct scope decision

The report narrows copilot to the quote **detail** page and explains why: the backend requires an
existing `quote_id`, and the builder is single-shot with no ID until after creation — at which
point it already redirects to the detail page. Extending copilot into the builder would mean
restructuring quote creation into a two-step flow. That's a sound call, correctly reasoned from the
backend contract rather than from convenience, and correctly declared rather than silently dropped.

## Acknowledged limitation — live browser verification

Not done, pre-declared: no reachable Docker daemon on this machine, so ai-service/quote-service
can't be brought up to click through the flow. Handed to Agent 3
([T202b live-verification handoff](T202b-live-verification-antigravity-handoff.md)). Same standard
as T204b/T307b/T311.

## Carried forward

| Gap                                                                                       | Tracked as      |
| ----------------------------------------------------------------------------------------- | --------------- |
| "Add to Quote" is a non-idempotent POST with no added-state → silent duplicate line items | **T202c** (new) |
| Shared pending/error state across suggestion rows                                         | **T202c**       |
| Missing `<label>` on both textareas                                                       | **T202c**       |
| End-to-end click-through against a running backend                                        | Agent 3 handoff |
