# CTO Audit — T203 (M8 Proposal Builder)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-07-28
- **Built by:** Agent 2
- **Verdict:** ✅ **Signed off** — no reservations on anything runnable in this environment; one
  known gap (live-Postgres path) carried forward, same class of gap already open on T206/T207 and
  now consolidated under [T311](../../TASKS.md) for Agent 3 to close.

## What was independently re-run (not taken on the commit notes' word)

| Check | Claimed | Actually observed |
| --- | --- | --- |
| `services/proposal-service` pytest | 30/30 | **32/32 passed** |
| `services/proposal-service` ruff | clean | clean |
| `services/proposal-service` mypy | clean | clean |
| `apps/api-gateway` vitest | 19/19 | **20/20 passed** |
| `apps/web` vitest | 71/71 | **71/71 passed** (8 files) |
| `apps/web` typecheck | clean | clean |
| `apps/web` `next build` | 14/14 routes | **14/14 routes, zero errors** |
| `scripts/check_conventions.py` | OK | **OK** |
| `scripts/run_all_tests.py` (all 6 backend services) | — | **all pytest/ruff/mypy green** |

(Test counts came in slightly higher than the commit notes claimed — undercounting, not
overclaiming. No red flags.)

## Spot-checks of the specific claims in the commit history

- **Gateway bare-prefix fix** (`apps/api-gateway/src/plugins/proxy.ts`) — confirmed real: find-my-way's
  `${prefix}/*` wildcard genuinely does not match the bare prefix, so `GET /v1/quotes` etc. were
  404ing through the real gateway before this. Fixed by registering the handler at both the bare
  prefix and the wildcard.
- **Identity-header stripping** (same file) — confirmed and important: `x-tenant-id`/`x-user-id`/
  `x-user-roles` are now deleted unconditionally before the auth block re-populates them. This
  matters specifically because of the next item.
- **Public `/view` route** (`app/interface/proposal_routes.py`) — the only intentionally
  unauthenticated route in the codebase. It resolves its own tenant via a narrow
  `SECURITY DEFINER` SQL function (`resolve_proposal_tenant`, `infra/db/migrations/0006_proposal.sql`)
  that returns **only** `tenant_id` — nothing else — which is the right way to bypass RLS for exactly
  one lookup without exposing a broader hole. Combined with the header-stripping fix above, a caller
  cannot spoof `x-tenant-id` to reach this route and see another tenant's data through the gateway.
- **PDF preview via authenticated route, not the public link** (`apps/web/.../proposals/[id]/page.tsx`)
  — confirmed, and the reasoning in the code comment is sound: the contractor's own copy of the
  `/view` link is deliberately rendered as plain text, not a clickable link, because opening it
  would flip the proposal to `VIEWED` and stamp `viewed_at` — destroying the one signal (did the
  *customer* open it) this feature exists to capture.
- **Status query param via typed enum** (`list_proposals`) — confirmed:
  `Query(default=None, alias="status")` typed as `ProposalStatus | None`, not manual string handling.
- **`proposal_status` enum `values_callable`** — confirmed already correct in
  `app/infrastructure/models.py` from the start (see T206b note below).

## The one gap (matches the existing T206/T207 pattern, not new)

Nothing in this environment can start a Postgres instance (`docker` isn't available on this
machine), so the following have only ever run against the SQLite test harness, never real Postgres:

1. The `SECURITY DEFINER` function itself (SQLite has no such concept — untestable here by
   construction, only exercised via a `FakeTenantResolver` seam in tests).
2. The full `create → send → view` happy path end-to-end.
3. Whether RLS actually blocks a cross-tenant read the way the code assumes.

This is the same class of gap flagged on T206 and T207, not a new one T203 introduced. Consolidated
with those into **T311**, assigned to Agent 3 — see `TASKS.md`.

## Correction made while auditing (unrelated to T203 itself)

`TASKS.md`'s "Check for Next Task" section still claimed *"the route calls `tenant_session()`
directly with no override seam, so there is no test asserting the 200 response body"* for T206's
summary endpoint. That's stale/wrong — `services/quote-service/tests/conftest.py`'s `api_session`
fixture monkeypatches `app.interface.routes.tenant_session` specifically because there's no
`Depends` to override, and `test_summary_endpoint_returns_the_full_contracted_body` does assert the
full 200 body against it. Corrected in this pass.
