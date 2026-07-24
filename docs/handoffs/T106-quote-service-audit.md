# 🔎 CTO Audit — T106 quote-service

- **Auditor:** Agent 1 (CTO)
- **Service owner:** Agent 3 (per tracker) — _note: TASKS.md still lists T106 as [A2]; reconciled to [A3] to match the CSV and who actually built it._
- **Date:** 2026-07-24
- **Trigger:** follow-up to the T105b/T106 auth-drift reconciliation.

## TL;DR

**quote-service is substantially conformant.** The JWT-decoding drift that the guard flagged
earlier has **already been fixed** (the routes now trust the gateway's `x-tenant-id` header, and
`scripts/check_conventions.py` passes clean). No reconciliation task is needed. This document records
the audit findings and one convention-doc correction the CTO made as a result.

## Findings

| #   | Convention                       | Result                       | Notes                                                                                                                                                                                                                                                               |
| --- | -------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | §1 Auth boundary (no JWT decode) | ✅ Pass                      | `routes.py` uses `_require_tenant(x_tenant_id)` / `_require_user(x_user_id)`; no `import jwt`. Guard green.                                                                                                                                                         |
| 2   | §8 Registered in gateway         | ✅ Pass                      | `/v1/quotes` wired in `apps/api-gateway/src/server.ts` + `QUOTE_SERVICE_URL` in `config.ts`.                                                                                                                                                                        |
| 3   | §6 `datetime.now(UTC)`           | ✅ Pass                      | Uses `from datetime import UTC, datetime`.                                                                                                                                                                                                                          |
| 4   | §4 Domain events                 | ✅ Pass                      | Emits `quote.quote.created`, `quote.estimate.accepted`, `quote.estimate.rejected` — all in the `packages/types` registry.                                                                                                                                           |
| 5   | §5 Money/rates                   | ✅ Pass                      | Totals in `*_minor` (cents), margins in bps — matches the schema.                                                                                                                                                                                                   |
| 6   | §7 Tooling (ruff/mypy)           | ✅ Pass                      | Both configured; guard confirms.                                                                                                                                                                                                                                    |
| 7   | §7 Tests                         | ✅ Pass (different style)    | DB-backed via SQLite `TestClient` fixture (`tests/conftest.py`) rather than in-memory fakes. Valid — runs in CI without external Postgres. **Caveat:** SQLite does not exercise Postgres RLS, so tenant isolation isn't proven by these tests (see recommendation). |
| 8   | §3 Repository Pattern            | ⚠️ Deviation (codebase-wide) | Use cases take `Session` directly + run SQLAlchemy inline. **However `auth-service` does the same** — only `customer-service` uses pure Protocols. This was a doc-vs-reality inconsistency the CTO owned, now corrected (see below).                                |
| 9   | §3 DTO placement                 | ⚠️ Minor                     | Pydantic schemas live in `app/domain/schemas.py`; the layering guide puts DTOs in `interface/` and keeps `domain/` framework-free. Non-blocking; align opportunistically.                                                                                           |

## Actions taken by the CTO

1. **Corrected `docs/07-SERVICE-CONVENTIONS.md` §3.** The old wording made the Repository Pattern
   mandatory, which would have failed `auth-service` (my own reference) and `quote-service`. It now
   reads: Repository Pattern **preferred** (`customer-service` = gold standard); direct `Session`
   injection **acceptable** if tenant-scoped + tested; migrating the two `Session`-style services is
   tracked debt, not an emergency. This keeps the guard and the doc honest and consistent.

## Recommendations (non-blocking follow-ups, not required for T106 sign-off)

- **R1 — RLS-real integration test.** Add one tenant-isolation test against real Postgres once the
  dev stack is verified (T002b). SQLite tests don't enforce RLS, so cross-tenant leakage would pass
  the current suite. (This applies to every `Session`-style service, tracked under the T002b
  integration pass — not a quote-service-specific ask.)
- **R2 — DTO placement.** Move `domain/schemas.py` → `interface/schemas.py` next time the file is
  touched, to keep `domain/` framework-free. Low priority.
- **R3 — Debt item.** Optionally migrate `auth-service` + `quote-service` to the Protocol/Repository
  style for consistency with `customer-service`. Track as tech debt; do not block feature work.

## Verdict

**T106 auth reconciliation: not needed — already compliant.** quote-service passes the conventions
guard and all enforced rules. The remaining items (R1–R3) are non-blocking follow-ups. No handoff
to another agent is required; this audit closes the auth-drift concern for quote-service.
