# 🔀 Handoff — T202b (M16 AI Copilot Web UI): live browser verification

- **From:** Agent 2 (Sonnet 5)
- **To:** **Agent 3 — Google Antigravity (Gemini)**
- **Assigned:** 2026-07-31
- **How to use this file:** paste this whole document as the first message into your next
  Google Antigravity session.

---

## Why you're getting this

T202b's implementation is done, task-reviewed clean across all 4 implementation tasks, and every
gate this machine's Claude Code session can run locally has passed. What's left is exercising it
live against running backend services in a browser — and per the same constraint noted in
[T307b-T311 handoff](T307b-T311-antigravity-handoff.md#why-youre-getting-both-of-these), this
machine has no reachable Docker daemon (`docker info` fails: `failed to connect to the docker API
at npipe:////./pipe/dockerDesktopLinuxEngine`), so `services/ai-service` and `services/quote-service`
can't be brought up locally here to click through the feature end-to-end. You're the one who's
already set up to spin up a disposable environment for this (same pattern as T002b/T311).

## What's already done (no action needed on these)

- Branch: `feat/t202b-ai-copilot-web-ui`, 4 commits, all task-reviewed clean.
- Spec: [M16 AI Copilot Web UI design](../superpowers/specs/2026-07-30-t202b-ai-copilot-web-ui-design.md).
- Plan: [M16-ai-copilot-web-ui-plan.md](../modules/M16-ai-copilot-web-ui-plan.md).
- `apps/web`: 94/94 vitest passing, `tsc --noEmit` clean, `next build` clean (`/quotes/[id]`
  route compiles at 6.03 kB, up from 3.76 kB pre-T202b — the new `CopilotPanel` +
  `InlineRewriteEditor` are in the bundle).
- No backend or gateway code changed — T202's already-signed-off `/v1/ai/copilot/*` endpoints and
  quote-service's existing line-item routes are consumed as-is, unmodified.

## What's needed from you

1. Bring up the dev stack (`pnpm dev:up` for the Docker services, then the usual local `pnpm dev`
   for `apps/web` + `apps/api-gateway`, or your disposable-VM equivalent if that's more reliable on
   your machine).
2. Check out `feat/t202b-ai-copilot-web-ui` (or pull it if already merged to `main` by the time you
   read this — check `TASKS.md`'s T202b row first).
3. Navigate to an existing quote's detail page (`/quotes/{id}`) with at least one line item, and
   run through the plan's Task 5 Step 2 exactly (quoting it here so you don't need to open the plan
   file to find it):
   1. Confirm the "AI Copilot" card renders below Line Items.
   2. Click "Analyze Pricing" on a quote with line items — confirm the margin block and per-line
      suggestions render, and clicking "Apply suggested markup" on a suggestion updates that line's
      markup/price in the Line Items table above (query invalidation working).
   3. Click "Find Missing Items" (with or without a job description) — confirm a completeness score
      and missing-item list render, and clicking "Add to Quote" on one adds a new $0 line item to
      the table above.
   4. Click the pencil icon next to a line item's description — confirm the inline editor opens;
      "Rewrite" replaces the textarea text with the AI's rewritten version; "Save" persists it and
      closes the editor, reflecting the new description in the table; "Cancel" discards without
      saving.
   5. Trigger at least one error path (stop `ai-service`, or exceed the daily spend cap if feasible)
      and confirm a real user-facing message renders (from `describeAiSubmitError`) instead of a raw
      status code.
4. Report results the same way T002b/T311 did: paste what you saw (or screenshots) into a Results
   section, tear down anything you spun up, and flip T202b's live-verification note in `TASKS.md` +
   `tracking/PROGRESS-TRACKER.csv` once confirmed.

## Standing rules (same as always)

- This is Agent 2's app (`apps/web`) — if you find a bug, prefer reporting it precisely (file, line,
  repro steps) over silently patching around it; if it's a one-line fix, flag clearly in your commit
  message that you touched Agent 2's folder and why.
- `check_conventions.py` / ruff / mypy aren't relevant here (no backend code changed), but re-run
  `apps/web`'s `pnpm vitest run && pnpm typecheck` if you touch anything.
