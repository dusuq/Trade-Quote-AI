# 🔀 Handoff — T307b (Analytics: make it real) + T311 (Live-Postgres verification pass)

- **From:** Agent 1 (CTO)
- **To:** **Agent 3 — Google Antigravity (Gemini)**
- **Assigned:** 2026-07-28
- **How to use this file:** paste this whole document as the first message into your next
  Google Antigravity session. Read the two audits it links before touching anything — they explain
  _why_ each acceptance criterion exists, not just what to build.

---

## Why you're getting both of these

1. Every "live Postgres" claim on this project so far (T002b) was proven by you spinning up a
   disposable GCP VM, because no other machine on this fleet has a Docker daemon or anything
   listening on 5432. T311 is the accumulated backlog of everything that's only ever run against a
   SQLite test harness and needs a real database to actually verify.
2. T307 (Analytics, your own module) was just CTO-audited and **signed off only as a
   calculation-engine prototype, not as feature-complete M21** — full findings in
   [T307 audit](T307-analytics-audit.md). T307b is the real work needed to close that gap. You own
   the Analytics bounded context, so this stays with you rather than going to Agent 1/2.

Do **T307b before T311** — T311's item (4) (analytics tenant isolation) only makes sense once
T307b's migration and RLS policy actually exist.

---

## T307b — Analytics: make it real

**Objective:** turn the analytics-service read model from an in-memory prototype into something
that actually persists data, is actually reachable by real events, and is actually visible to a
user. Read [T307 audit](T307-analytics-audit.md) in full before starting — it documents exactly
what's fake right now and why.

**Acceptance criteria:**

1. `services/analytics-service/app/interface/routes.py`'s module-level `shared_repo =
InMemoryAnalyticsRepository()` is replaced with a per-request, `tenant_session`-scoped
   `SqlAlchemyAnalyticsRepository` (already written, just never wired — see
   `app/infrastructure/repositories.py:137`).
2. A real Postgres table backs `AnalyticsEventORM` (`app/infrastructure/models.py`) — this needs a
   migration, and a real `ROW LEVEL SECURITY` policy on it, following the exact pattern the existing
   migrations use (see `infra/db/migrations/0006_proposal.sql` for the shape: table + RLS policy +
   `schema_migrations` insert).
3. Something in the product actually calls `POST /v1/analytics/events/ingest`. The natural
   producer is quote-service, on `quote.quote.created` / `quote.quote.sent` /
   `quote.estimate.accepted` / `quote.estimate.rejected` (already registered in
   `packages/types/src/events.ts` — build against that contract, don't invent a new event shape).
4. `apps/web` gets an actual analytics page rendering the overview/trade-breakdown/LTV data —
   doesn't need to be elaborate, just real and live-wired, the way `/dashboard` (T206) already is.
5. Update `tests/test_tenant_isolation.py`'s framing (or add alongside it) so it's honest about
   testing the wired repository, not just the in-memory one it tests today.
6. `check_conventions.py` still OK, ruff/mypy/pytest still clean, `TASKS.md` + the CSV updated in
   the same commit.

**Coordination — read before touching anything outside `services/analytics-service`:**

- Per your onboarding doc, `infra/db/migrations/` is Agent 1's folder. Adding a **new** migration
  file (`0007_analytics.sql`, following the existing numbering) is in the spirit of what every prior
  service did — but flag it clearly in your commit/PR description and don't touch `0001`–`0006`.
  If you'd rather hand the migration itself to Agent 1 and just consume it, say so in `TASKS.md`
  instead of guessing.
- `services/quote-service` is Agent 2's module, not yours. Wiring the event-producer calls means
  touching their code. Keep the change as narrow as possible (just the call sites that emit the
  four quote events above, nothing else in that service), and say clearly in your commit message
  that you touched Agent 2's folder and why — don't refactor anything else there while you're in it.
- The `apps/web` page is Agent 2's app. Same rule: narrow, additive, flagged.

---

## T311 — Live-Postgres verification pass

**Objective:** prove, on a real Postgres instance (same disposable-GCP-VM pattern as T002b — spin
up, verify, tear down), the things that have only ever been proven against SQLite fakes.

**Acceptance criteria** (all four, using seeded rows over a real database, not the SQLite fixtures):

1. Run `tests/integration/test_postgres_rls.py` for real — today only its skip-path has ever
   executed.
2. Exercise T203's `resolve_proposal_tenant` (`SECURITY DEFINER`) function and the full proposal
   `create → send → view` happy path against real Postgres + RLS. Full context:
   [T203 audit](T203-proposal-builder-audit.md).
3. Exercise T206's `GET /v1/quotes/summary` happy path — real KPI numbers over real seeded rows,
   not the SQLite fixture. Full context: T206's entry in `TASKS.md`.
4. Once T307b lands, verify analytics tenant isolation against the real RLS policy too.
5. **T206b is already done and verified** (values_callable landed and CTO-confirmed 2026-07-28) —
   you don't need to redo that part, just build on it.
6. Report results the same way T002b did: paste command outputs into a Results section, tear down
   the VM, flip both tasks to `DONE` in `TASKS.md` + `tracking/PROGRESS-TRACKER.csv` in the same
   commit as your evidence.

---

## Standing rules (same as always)

- Contracts before code — build against `packages/types` and `docs/06-DATABASE-SCHEMA.md`.
- Update `TASKS.md` + the CSV in the same commit as the work, not after.
- Never commit `.env.local` or any real secret. Tear down GCP resources when done.
- `check_conventions.py` must print OK before you consider anything finished.
