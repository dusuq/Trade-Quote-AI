# 🔀 Handoff — T204b (M10 E-Signature Web UI): live browser verification

- **From:** Agent 2 (Sonnet 5)
- **To:** **Agent 3 — Google Antigravity (Gemini)**
- **Assigned:** 2026-07-31
- **How to use this file:** paste this whole document as the first message into your next
  Google Antigravity session.

---

## Why you're getting this

T204b's implementation is done, task-reviewed clean across all 8 implementation tasks, and a
final whole-branch review found and fixed 2 Important cross-cutting issues (see `TASKS.md`'s
T204b row for the summary). Every gate this machine's Claude Code session can run locally has
passed. What's left is exercising it live against running backend services in a browser — and
per the same constraint noted in
[T307b-T311 handoff](T307b-T311-antigravity-handoff.md#why-youre-getting-both-of-these) and
[T202b's equivalent handoff](T202b-live-verification-antigravity-handoff.md), this machine has
no reachable Docker daemon, so `services/esign-service`, `services/proposal-service`, and
`services/quote-service` can't be brought up locally here to click through the feature
end-to-end. You're already set up to spin up a disposable environment for this (same pattern
as T002b/T311).

## What's already done (no action needed on these)

- Branch: `feat/t204b-esignature-web-ui`, based on the architecture plan Agent 1 (CTO) prepared
  ([M10-esignature-web-ui-plan.md](../modules/M10-esignature-web-ui-plan.md)) and my own
  9-task execution plan ([M10-esignature-web-ui-execution-plan.md](../modules/M10-esignature-web-ui-execution-plan.md)).
- `apps/web`: 109/109 vitest passing, `tsc --noEmit` clean, `next build` clean (17 routes,
  including the new `/proposals/signatures` and `/sign/[token]`).
- No backend or gateway code changed — T204's already-signed-off `/v1/signature-requests` and
  `/v1/sign` endpoints (already public/gateway-reachable since T204) are consumed as-is.
- Two legally-significant bugs were caught and fixed during review before this handoff:
  1. A signature request could previously be requested on a still-DRAFT proposal, whose public
     PDF view 404s by design — the signer could never see the document, yet nothing blocked
     signing. Fixed: "Request E-Signature" now only shows once the proposal is sent/viewed.
  2. The client was sending the server's own claimed document hash back as the signing
     payload's `document_sha256`, instead of the hash it actually computed from the PDF it
     fetched — a tautological check that made tamper detection (`DocumentMismatchError`)
     unreachable. Fixed: the payload now carries the locally-computed hash, and the Sign
     button is disabled entirely if the PDF never successfully loaded/hashed.

## What's needed from you

1. Bring up the dev stack (`pnpm dev:up` for the Docker services, then `pnpm dev` for
   `apps/web` + `apps/api-gateway`, or your disposable-VM equivalent).
2. Check out `feat/t204b-esignature-web-ui` (or pull it if already merged to `main` by the time
   you read this — check `TASKS.md`'s T204b row first).
3. On a **sent or viewed** proposal (not draft — the button won't show on a draft; if you need
   one, send a draft proposal first from `/proposals/{id}`), run through these:
   1. Click "Request E-Signature", fill in a signer name/email, submit — confirm it fetches
      the PDF, computes its hash, and the new request appears in the "Signature Requests" card
      with a "pending" badge.
   2. Click "Copy Link" — confirm it copies a working `http://localhost:.../sign/{token}` URL
      (your own web app's origin, NOT the API gateway's origin) and that clicking Copy Link
      twice quickly doesn't produce a stale/wrong token (it re-fetches fresh each click).
   3. Open the copied link in a new incognito/private tab (simulating the unauthenticated
      customer) — confirm the PDF preview loads, the "Document integrity verified" banner
      shows green, and both the Type and Draw signature tabs work (drawing actually tracks
      your cursor across the full width of the canvas — this was a real bug that got fixed;
      worth specifically confirming strokes don't drift/clip).
   4. Try clicking Sign with only one of the two consent checkboxes checked — confirm the
      button stays disabled. Check both, then sign — confirm the success receipt shows a
      transaction ID, hash, and timestamp.
   5. Back on the proposal detail page, confirm the request's badge flipped to "signed" and
      click "View Audit" — confirm the hash-chain timeline renders with a green "Chain
      Verified" badge and the captured signature's metadata (name, IP, method, consent/intent).
   6. Create a second signature request, open its link, and click "Decline to Sign" (with the
      confirm dialog) instead — confirm it shows the decline message and the request's badge
      flips to "declined" back on the contractor side.
   7. Try voiding a still-pending request from the contractor side — confirm the confirm()
      dialog appears, and after confirming, the badge flips to "voided" and the Void button
      disappears for that row (it only shows on `pending`).
   8. Visit `/proposals/signatures` and confirm the status filter tabs (All/Pending/Signed/
      Declined/Voided/Expired) actually filter the list, and each row's "View proposal" link
      goes to the right proposal.
   9. Try an already-used or fabricated `/sign/{token}` link — confirm it shows "This signing
      link is no longer valid," not a raw error or blank page.
4. Report results the same way T002b/T311 did: paste what you saw (or screenshots) into a
   Results section, tear down anything you spun up, and flip T204b's live-verification note in
   `TASKS.md` + `tracking/PROGRESS-TRACKER.csv` once confirmed.

## Standing rules (same as always)

- This is Agent 2's app (`apps/web`) — if you find a bug, prefer reporting it precisely (file,
  line, repro steps) over silently patching around it; if it's a one-line fix, flag clearly in
  your commit message that you touched Agent 2's folder and why.
- `check_conventions.py` / ruff / mypy aren't relevant here (no backend code changed), but
  re-run `apps/web`'s `pnpm vitest run && pnpm typecheck` if you touch anything.
