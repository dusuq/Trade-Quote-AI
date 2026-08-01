# CTO Audit — T204b (M10 E-Signature web UI)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-08-01
- **Built by:** Agent 2
- **Verdict:** ✅ **Signed off.** Every gate claim reproduced exactly, and — the part that matters —
  both security-critical claims are true in the code, not just in the report. Two minor findings,
  neither blocking. One real gap is **mine**, not Agent 2's: the backend this UI talks to takes
  `proposal_id` and `document_sha256` entirely on trust.

## Gates — all four reproduced

| Claim | Result |
| --- | --- |
| 109/109 web tests | **109 passed** (11 files) |
| `tsc --noEmit` clean | clean, exit 0 |
| `next build` clean, 17 routes | clean — **exactly 17**, `/sign/[token]` present as a dynamic route |
| Gateway 30/30 | **30 passed** |

## The two security claims — both true

This task's report makes two specific claims about defects caught in final review. Reports like
that are worth checking precisely because they are the easiest place to overstate. Both hold.

### 1. The signing payload carries the *locally computed* hash

The claim is that `document_sha256` was previously the server's own value echoed back — a
tautological self-comparison that made the backend's `DocumentMismatchError` structurally
unreachable. Fixed, and correctly:

```tsx
const hash = await computeSha256(await blob.arrayBuffer());
setComputedDocumentSha256(hash);
setDocumentVerified(hash === context.document_sha256);   // client-side indicator
...
document_sha256: computedDocumentSha256,                  // what is actually submitted
```

The submitted value is the hash the browser computed from the PDF it fetched, so the backend's
tamper check now compares two independently-sourced values and can actually fail. The check is
also genuinely cross-service: `context.document_sha256` comes from esign-service's stored
signature-request row, the PDF from proposal-service. It therefore detects the case that matters —
the document being swapped *after* the request was created.

The second half of the claim is true too: `canSign` requires `computedDocumentSha256 !== null`, so
the Sign button is disabled outright when the PDF never loaded or hashed, rather than erroring at
submit. `computeSha256` produces lowercase hex via `padStart(2, "0")`, matching the backend's
`_SHA256_HEX` pattern and its case-normalizing validator.

Worth noting deliberately: a signer **can** still submit when the integrity indicator shows a
mismatch. That is the right call — the client-side badge is advisory, and the server is the
authority that rejects it with a 409. Blocking client-side would add nothing and would hide the
real check.

### 2. Draft proposals no longer offer a signing request

`proposal.status !== "draft"` gates the "Request E-Signature" button
([proposals/[id]/page.tsx:128](../../apps/web/src/app/(app)/proposals/[id]/page.tsx)). Correct: a
draft's public `/view` 404s by design, so the signer could never see the document.

## What I checked that the report doesn't claim

**The public page is genuinely reachable unauthenticated.** A signing page that the app's own auth
layer redirects to `/login` is a classic way for this feature to be silently broken. It isn't:
there is no `middleware.ts`, the root layout has no auth guard, and `sign/` is a sibling of the
`(app)` and `(auth)` route groups rather than a child — so it does not inherit the app shell's
protection. `fetchPublicProposalPdfBlob` uses raw `fetch` with no bearer header and carries an
explicit comment telling contractor-facing code to use the authenticated variant instead.

**The audit dialog surfaces the server's verification rather than reimplementing it.** It renders
`is_valid`, `broken_at_sequence`, and `reason` straight from T204's response. That is the correct
division — a client cannot independently verify a hash chain, and a client-side "verified" badge
computed locally would be theatre.

**The `signingToken` naming discipline is real, not just documented.** All three public functions
take `signingToken`; the authenticated ones take `token` (a bearer JWT). `SignatureRequestDetail`
carries a comment warning that list rows deliberately do not include a usable token.

## Finding — non-blocking: a bare status code can still reach the user

`RequestSignatureDialog` handles its own errors inline rather than through a shared mapper:

```tsx
setError(err instanceof ApiError ? err.message : "Couldn't create the signature request.");
```

`canSubmit` checks only name and email, not `expiresInDays`. The field is `type="number"` with
`min={1} max={365}`, but there is no `<form>` and no validity check, so those attributes are
decorative — clearing the field yields `Number("") === 0`, which submits. The backend correctly
rejects it (`expires_in_days: int = Field(default=30, ge=1, le=365)`), but FastAPI sends
`{"detail": [...]}` and `apiFetch` reads only `data.message`/`data.error`, so the fallback fires
and the user sees **`Request failed with status 422`**.

This is the same class of defect Agent 2 correctly fixed in T201b (`write-scope-panel.tsx`
bypassing `describeAiSubmitError` and surfacing a bare 429). Note that `describeEsignSubmitError`
is *not* the right mapper to reuse here — its 422 case is signer-specific ("confirm both consent
checkboxes"). The fix is to validate `expiresInDays` in `canSubmit`, and give this surface its own
422 message. Tracked in **T204c**.

## Finding — non-blocking: `aria-modal` without a focus trap

`Dialog` sets `role="dialog"` and `aria-modal="true"`, closes on Escape and backdrop click, and is
honest in its own docstring: *"Does not trap focus - no multi-step keyboard-only flow uses this
yet, so keep anything rendered inside simple."*

I like that the limitation is written down. The problem is that its first consumer is a three-field
form, so the stated assumption is already mildly violated. `aria-modal="true"` tells assistive
technology that everything outside is inert, which is not true here — focus can tab out to the page
behind, and focus is neither moved into the dialog on open nor restored to the trigger on close.
Low severity (both dialogs are short and mouse-friendly), but the attribute currently overstates
what the component does. Either add the trap or drop `aria-modal`. Tracked in **T204c**.

## Finding — this one is mine, from T204

The report is careful to say the two UI fixes compose into defence-in-depth *"even though no
backend guard blocks creating a request on a draft."* That is accurate, and it is worth stating
plainly what it means: **esign-service never contacts proposal-service at all.** I grepped for it —
there is no `ServiceClient`, no `httpx`, no proposal-service URL anywhere in the service.

So `proposal_id` and `document_sha256` are accepted entirely on the client's word. Consequences:

- The draft guard is **UI-only**. `POST /v1/signature-requests` will still create a request against
  a draft. It fails safe — the signer's PDF fetch 404s, `computedDocumentSha256` stays null, and
  Sign is disabled — but it produces a dead request and an audit-trail entry for a document nobody
  could ever see.
- There is no check that the proposal exists or belongs to the caller's tenant. This is **not** a
  new disclosure — T203's `/view` is already an id-as-capability route, so anyone holding a
  proposal UUID can fetch that PDF regardless. But it does mean the hash-chained, legally-framed
  audit record can be bound to a proposal reference the service never validated.

Fixing this is a synchronous call that is genuinely *part of fulfilling the request*, so ADR-0003
permits it: validate the proposal on create, with an explicit timeout, mapping failure to
`UpstreamServiceError`. Tracked in **T204c**, owned by me.

## Acknowledged limitation — live browser verification

Not done, and pre-declared rather than glossed: this machine has no reachable Docker daemon, so
esign-service/proposal-service/quote-service can't be brought up to click through the flow. Handed
to Agent 3 with a written brief
([T204b live-verification handoff](T204b-live-verification-antigravity-handoff.md)). Same standard
applied to T307b/T311/T202b.

## Carried forward

| Gap | Tracked as |
| --- | --- |
| `expiresInDays` unvalidated client-side; 422 surfaces as a bare status code | **T204c** (new) |
| `aria-modal="true"` without focus trap / focus restoration | **T204c** |
| esign-service validates neither `proposal_id` nor proposal status (**Agent 1's gap**) | **T204c** |
| End-to-end click-through against a running backend | Agent 3 handoff |
