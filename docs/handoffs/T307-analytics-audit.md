# CTO Audit — T307 (M21 Analytics)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-07-28
- **Built by:** Agent 3 (Antigravity)
- **Verdict:** ⚠️ **Signed off only as a calculation-engine prototype — NOT as feature-complete M21
  Analytics.** Unlike T203/T206 (whose only gap was "can't verify against live Postgres in this
  sandbox"), this task's gaps are **coding gaps, not environment gaps** — the service as built
  cannot do its job in any deployment, Docker or not, because nothing wires it end-to-end. The
  original tracker language ("Repository Pattern protocol... strict RLS tenant isolation suite")
  overstates what's actually there. Follow-up tracked as **T307b**.

## What was independently re-run

| Check                               | Claimed | Actually observed                                                                                                                     |
| ----------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `services/analytics-service` pytest | 9/9     | **9/9 passed** — accurate                                                                                                             |
| ruff / mypy                         | clean   | clean — accurate                                                                                                                      |
| `check_conventions.py`              | OK      | OK — accurate (`_require_tenant` correctly trusts `x-tenant-id`, never decodes a JWT)                                                 |
| Gateway route `/v1/analytics`       | wired   | **confirmed** — `registerServiceProxy` + `ANALYTICS_SERVICE_URL` (sane default `:8006`)                                               |
| Repository Pattern protocol         | claimed | **genuine** — `AnalyticsRepositoryProtocol` is a real `Protocol`, `AnalyticsService` depends on the abstraction, not a concrete class |

The test count and code-quality claims are all accurate. The problem is what the tests and the
"Repository Pattern" framing quietly don't tell you.

## What's actually wrong

1. **No persistence in the path that's actually running.** `app/interface/routes.py` uses a
   module-level singleton: `shared_repo = InMemoryAnalyticsRepository()` — a plain Python list held
   in process memory. Every event ingested is gone on the next restart, and isn't shared across
   multiple worker processes/instances either.
2. **The "production" repository is dead code.** `SqlAlchemyAnalyticsRepository` and
   `AnalyticsEventORM` exist in `app/infrastructure/repositories.py` / `models.py` — grepped every
   reference across the app and test suite; the only place `SqlAlchemyAnalyticsRepository` appears
   is its own class definition. Nothing constructs it. It would also fail immediately if something
   did, because:
3. **There is no database migration for the table it maps to.** `infra/db/migrations/` stops at
   `0006_proposal.sql`. There is no `0007_analytics.sql`. `analytics_events` doesn't exist in any
   environment, live Postgres or otherwise.
4. **The "strict RLS tenant isolation suite" claim is a mischaracterization.** `db.py`'s
   `tenant_session()` calls `SELECT set_config('app.current_tenant', ...)`, mirroring the pattern
   used by services that really do have Postgres RLS — but there is no `ROW LEVEL SECURITY` policy
   defined anywhere for this (nonexistent) table. `tests/test_tenant_isolation.py` genuinely does
   verify tenant A never sees tenant B's data — but it does so by exercising the **in-memory**
   repository's Python list-comprehension filtering (`[e for e in self.events if e.tenant_id ==
tenant_id]`), through the FastAPI `TestClient`. That's a legitimate, well-written application-level
   test. It is not RLS. RLS is a database-enforced guarantee that holds even if the application query
   is wrong; this is app-level filtering with no defense-in-depth. Calling it "RLS" in the tracker
   overstates the security guarantee actually in place.
5. **Nothing in the product ever calls `POST /v1/analytics/events/ingest`.** Grepped
   `services/quote-service` and `services/proposal-service` — the two bounded contexts that would
   naturally emit `quote.quote.created` / `quote.quote.sent` / `quote.estimate.accepted` /
   `quote.estimate.rejected` (all already registered in `packages/types/src/events.ts`) — zero
   references to analytics anywhere. The ingest endpoint works and is well-tested in isolation, but
   in any real deployment today the overview/trade-breakdown/LTV endpoints would return empty data
   forever, because nothing ever populates them.
6. **No web UI.** Grepped `apps/web/src` for "analytics" — zero matches. Unlike T206's dashboard,
   which is genuinely live-wired into a page, there is no user-facing surface for any of this yet.
7. Minor: no `docs/modules/M21-*.md` spec/plan doc exists, unlike T203/T206/T105/T106.

## Why this isn't folded into T311

T311 (the Docker/Postgres verification backlog) exists because certain things are _already built
correctly_ and simply can't be exercised against a live database on this fleet's machines. That's
not what's happening here — items 1, 2, 3, 5, and 6 above are missing code, not missing
infrastructure. Adding a migration, swapping the wired repository, adding event-producer calls, and
building a UI all have to happen regardless of who eventually runs it against real Postgres.
Verifying the RLS policy once it exists _would_ then roll into T311's scope.

## Corrections made to the trackers

- `TASKS.md` / `PROGRESS-TRACKER.csv`: T307's "Quality Gates Passed" was already blank (no CTO
  sign-off had been recorded) — now filled in with this conditional verdict instead of silently
  promoting it to a full sign-off.
- Removed "strict RLS tenant isolation suite" language; replaced with an accurate description
  (in-memory repository, app-level tenant filtering, tested and correct as far as it goes).
- Added **T307b**: wire real persistence (add the missing migration + an actual RLS policy on
  `analytics_events`, swap `shared_repo` for a per-request `tenant_session`-scoped
  `SqlAlchemyAnalyticsRepository`), wire event-producer calls from quote-service (and
  proposal-service where relevant) into the ingest endpoint, and build the web analytics page.
  Owner: Agent 3 (existing owner of the Analytics bounded context); the web-UI slice may need
  Agent 2's involvement since they own `apps/web`.
