# T206 — M20 Dashboard · Design Spec

| Field            | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| **Task**         | `T206`                                                       |
| **Module**       | M20 — Dashboard                                              |
| **Owner agent**  | Agent 2 (Sonnet 5)                                           |
| **Phase**        | Phase 2 — AI + Delivery                                      |
| **Dependencies** | `T106` quote-service ✅ · `T108` web shell ✅                 |
| **Date**         | 2026-07-25                                                   |
| **Status**       | Design approved — ready for implementation planning          |
| **Bounded ctx**  | `services/quote-service` (read model) + `apps/web` (UI)      |

---

## 1. Problem

`apps/web/src/app/(app)/dashboard/page.tsx` is a static placeholder: four KPI cards
rendering `"—"` and a Recent Quotes card with no data. Its inline comment claims the page
"wires to `services/analytics-service` (M21/T307) once it ships" — **this is wrong and is
removed by this task.** T307 is a Phase 3 forecasting service owned by Agent 3; every KPI
in the T206 scope line (quotes today / pending / accepted / revenue / conversion) is
derivable from the quote aggregate alone. Waiting on T307 would block a Phase 2 deliverable
behind a Phase 3 service for no reason.

Meanwhile `quote-service` holds everything needed — `status`, `total_minor`, `currency`,
`created_at` — but exposes only `GET /v1/quotes` with `limit ≤ 500`, and no aggregation.

## 2. Decisions

### D1 — Aggregation lives in `quote-service` as a CQRS read model

A new `GET /v1/quotes/summary` endpoint computes the KPIs in SQL.

**Rejected alternatives:**

- _Client-side aggregation in `apps/web`._ Zero backend risk and fastest to ship, but
  `GET /v1/quotes` caps at 500 rows per page, so accepted value and conversion would
  silently go wrong for any real shop. Ships work that must later be thrown away.
- _Stand up `services/analytics-service` now._ Architecturally the long-term home per
  AGENTS.md's M20 row, but it is Agent 3's Phase 3 service (M21), requires an event bus
  that does not yet exist, and would gate five KPIs behind an entire new service.

**Why D1 wins:** quote data stays inside its own bounded context (no cross-context reach),
SQL aggregation scales past the list cap, and `M7 quote-service` is Agent 2's module per
AGENTS.md so no cross-agent handoff is required. CQRS-where-appropriate is an explicit
engineering standard in the CTO directive.

### D2 — "Today" is resolved from a client-supplied IANA timezone

No timezone column exists anywhere in the schema (`tenant` carries `country`, nothing
temporal; zero timezone references across all services and migrations). The client sends
`?tz=Australia/Sydney`; the server validates it and computes day boundaries in that zone,
falling back to UTC when the parameter is absent.

**Rejected alternatives:** a `tenant.timezone` migration (correct long-term, but edits
Agent 1's M3 schema, needs a settings UI to be usable, and blocks the dashboard on a
cross-module change) and UTC-only (a Sydney contractor at 09:00 Monday sees UTC Sunday —
their whole morning counted as yesterday, in a market the CTO directive explicitly targets).

**Absent vs invalid are treated differently.** An absent `tz` falls back to UTC; an
_invalid_ one returns `400` rather than also falling back. A typo'd zone that silently
degrades to UTC would hand the user confidently wrong day counts with no signal that
anything went wrong — the failure mode this decision exists to prevent. A caller that
genuinely wants UTC omits the parameter.

### D3 — Boundary math in Python, not Postgres SQL

`quote-service` tests run against **SQLite in-memory** (`tests/conftest.py`), so
Postgres-only `date_trunc(...) AT TIME ZONE` would be untestable in CI. Day and range
boundaries are computed in Python with stdlib `zoneinfo` and passed into the query as
explicit UTC datetime parameters, keeping the SQL portable across SQLite and Postgres.

Constructing `ZoneInfo(tz_name)` doubles as the validator: an unknown zone raises
`ZoneInfoNotFoundError`, which maps to `400`.

### D4 — "Revenue" is named "Accepted Value"

The T206 scope line says _revenue_, but the value of accepted estimates is not collected
money — payments are M11/T303 in Phase 3. A card labelled "Revenue" would misstate a
contractor's finances to them. The field is `accepted_value_minor`; the card reads
**"Accepted Value (MTD)"**.

### D5 — Ranges are cohort-based, keyed on `created_at`

There is no `accepted_at` column, and `updated_at` moves on any edit, so it is an unsound
proxy for "when this was accepted". MTD therefore means: _of the quotes **created** this
month, N are accepted, worth $X._

This needs no migration and is methodologically sounder for conversion — it compares one
cohort's outcomes instead of mixing this month's wins against last month's sends.

### D6 — Currency totals are never summed across currencies

Quotes carry a per-quote `currency`. Accepted value is returned as an array grouped by
currency. Single-currency tenants (the overwhelming majority) render one figure; a mixed
tenant sees one line per currency rather than a meaningless cross-currency sum.

## 3. KPI definitions

| Card               | Response field                      | Definition                                                              |
| ------------------ | ----------------------------------- | ----------------------------------------------------------------------- |
| Quotes Today       | `quotes_today`                      | Quotes created within the tz-local calendar day                         |
| Pending            | `pending_count`                     | **Point-in-time**: current status ∈ {`sent`, `viewed`}, any create date |
| Accepted           | `accepted_count`                    | Of quotes created in range, those with current status `accepted`        |
| Accepted Value     | `totals[].accepted_value_minor`     | `sum(total_minor)` of those accepted quotes, grouped by currency        |
| Conversion         | `conversion_bps`                    | `accepted_count / decided_count` in basis points (0 when none decided)  |

`decided_count` = cohort quotes with status ∈ {`accepted`, `rejected`, `expired`}.

Two deliberate consequences:

- **Pending excludes `draft`** — a draft is the contractor's own unfinished work; `sent`
  and `viewed` are waiting on the customer.
- **Pending ignores the range filter** — a quote sent last month and still open is still
  pending today. It is the only point-in-time KPI on the page.

## 4. API contract

```
GET /v1/quotes/summary?tz=Australia/Sydney&range=mtd
```

| Parameter | Type                     | Default | Notes                                        |
| --------- | ------------------------ | ------- | -------------------------------------------- |
| `tz`      | IANA zone name           | `UTC`   | Invalid or unknown zone → `400`              |
| `range`   | `Literal["mtd", "ytd"]`  | `mtd`   | Anything else → `422` (FastAPI validation)   |

Headers follow conventions §1 — the gateway has already verified the JWT:
`x-tenant-id` (required), `x-user-id` (optional).

**`200 OK`**

```json
{
  "timezone": "Australia/Sydney",
  "range": "mtd",
  "range_start": "2026-07-01T00:00:00+10:00",
  "range_end": "2026-07-26T00:00:00+10:00",
  "quotes_today": 4,
  "pending_count": 12,
  "accepted_count": 31,
  "decided_count": 72,
  "conversion_bps": 4306,
  "totals": [{ "currency": "USD", "accepted_value_minor": 4820000 }]
}
```

`range_start` / `range_end` are echoed so the UI can label the card from the server's
own reckoning rather than recomputing the boundary and risking disagreement.

**`range_end` is the exclusive end of the current tz-local day**, not the end of the
calendar month — "to date" includes everything created today. It is therefore always equal
to the day boundary `day_end` used by `quotes_today`, which keeps the two windows
consistent: a quote created ten minutes ago counts toward both `quotes_today` and the MTD
cohort.

**No gateway change is required.** `apps/api-gateway/src/server.ts:39` proxies the
`/v1/quotes` prefix to `quote-service`, so `/v1/quotes/summary` is reachable immediately.

## 5. Backend design — `services/quote-service`

```
app/domain/summary.py       NEW   frozen dataclasses: QuoteSummary, CurrencyTotal, RangeBounds
app/application/summary.py  NEW   resolve_range(), summarize_quotes()
app/interface/schemas.py    EDIT  + QuoteSummaryResponse
app/interface/routes.py     EDIT  + GET /summary
```

Summary logic goes in a **new** `application/summary.py` rather than into
`application/services.py`, which is already 476 lines.

Domain value objects are plain frozen dataclasses — framework-free, so `domain/` keeps no
Pydantic dependency and the use case returns domain types rather than DTOs. This also
avoids repeating the DTO-placement issue flagged as R2 in the T106 audit.

### 5.1 `resolve_range(tz_name: str | None, range_key: str) -> RangeBounds`

Pure, no I/O. Validates the zone, then returns UTC instants for the tz-local day
(`day_start`, `day_end`) and the tz-local range (`range_start`, `range_end`), plus the
resolved zone name for echoing. Because it touches no database, every timezone concern —
Sydney offsets, DST transition days, invalid names — is unit-testable in isolation.

### 5.2 `summarize_quotes(session, tenant_id, bounds) -> QuoteSummary`

Three portable aggregate queries:

```sql
-- 1. quotes_today
count(*)  WHERE tenant_id = :t AND created_at >= :day_start   AND created_at <  :day_end

-- 2. pending_count (point-in-time, unfiltered by range)
count(*)  WHERE tenant_id = :t AND status IN ('sent', 'viewed')

-- 3. cohort roll-up — feeds accepted_count, accepted value, and conversion in one pass
status, currency, count(*), sum(total_minor)
          WHERE tenant_id = :t AND created_at >= :range_start AND created_at <  :range_end
          GROUP BY status, currency
```

Half-open intervals (`>= start`, `< end`) throughout, so a quote created exactly at
midnight is counted once and only once.

**The explicit `tenant_id` predicate is required, not redundant.** The SQLite test harness
has no RLS, so without it a tenant-isolation test would pass while proving nothing. With
it, the isolation assertion required by conventions §2 is genuinely enforced in CI —
significant because no service has yet run against live Postgres.

### 5.3 Route ordering — a real trap

`routes.py:88` declares `@router.get("/{quote_id}")` with `quote_id: uuid.UUID`. FastAPI
matches in registration order, so a `/summary` route declared **after** it is swallowed and
fails UUID parsing with a `422`.

`GET /summary` **must be declared above `get_quote`**, and a regression test asserts
`/v1/quotes/summary` returns `200` (not `422`) so that a future reordering fails CI instead
of silently breaking the dashboard.

### 5.4 Error handling

| Condition                | Response                                             |
| ------------------------ | ---------------------------------------------------- |
| Missing `x-tenant-id`    | `401` — reuses the existing `_require_tenant` helper |
| Unknown / invalid `tz`   | `400` "unknown timezone"                             |
| Invalid `range`          | `422` — FastAPI `Literal` validation                 |
| Tenant has no quotes     | `200` with zeros, `totals: []`, `conversion_bps: 0`  |

`decided_count` ships alongside `conversion_bps` specifically so the UI can distinguish
"nothing decided yet" (render `—`) from a genuine 0% close rate. Reporting a hard `0%` to a
contractor who simply has no decisions yet would be a lie.

## 6. Frontend design — `apps/web`

```
src/lib/dashboard.ts                       NEW   wire types, fetchQuoteSummary(), pure helpers
src/lib/dashboard.test.ts                  NEW   vitest unit tests for the pure helpers
src/lib/quotes.ts                          EDIT  listQuotes() gains an optional limit param
src/app/(app)/dashboard/page.tsx           EDIT  placeholder → live client component
```

`dashboard.ts` exports `fetchQuoteSummary(token, tz, range)` plus pure, separately testable
helpers: `resolveBrowserTimezone()` (via `Intl.DateTimeFormat().resolvedOptions().timeZone`),
`formatConversion(bps, decidedCount)` (returns `—` when `decidedCount === 0`), and
`pickPrimaryTotal(totals)`. This mirrors the existing `money.ts` / `quotes.ts` split of pure
logic from I/O, which is what makes those modules unit-testable today.

`dashboard/page.tsx` becomes a `"use client"` component using `useAuthGuard()` +
`useQuery`, following `quotes/page.tsx` exactly — same loading, error, and empty-state
treatment. The stale T307 comment is deleted. The existing local `KpiCard` component is
retained.

The Recent Quotes card reuses `listQuotes` with a new **optional** `limit` parameter
(backward-compatible; existing callers unaffected), rendering the 5 most recent quotes with
the existing `statusBadgeVariant` and `formatMoney` helpers, each linking to
`/quotes/[id]`.

## 7. Testing strategy

**`quote-service` — pytest (~10 tests)**

1. `resolve_range` — tz-local day boundary for `Australia/Sydney` vs `UTC`
2. `resolve_range` — DST transition day produces correct UTC instants
3. `resolve_range` — unknown zone raises, absent zone defaults to UTC
4. `resolve_range` — `mtd` vs `ytd` start instants
5. Aggregate — mixed statuses produce correct `quotes_today` / `pending_count` / `accepted_count`
6. Aggregate — `pending_count` includes an out-of-range quote (point-in-time semantics)
7. Aggregate — mixed currencies produce one `totals` row each, never summed
8. Conversion — `accepted / (accepted+rejected+expired)` in bps; `decided_count == 0` → `0`
9. **Tenant isolation** — a second tenant's quotes never appear (conventions §2)
10. **Route ordering** — `GET /v1/quotes/summary` returns `200`, not `422`

**`apps/web` — vitest (~7 tests)** covering `formatConversion` (including the `—` case),
`pickPrimaryTotal` (empty / single / multi-currency), `resolveBrowserTimezone`, and the
`fetchQuoteSummary` request shape and error propagation.

**Gates:** `ruff check` · `mypy app` · `pytest` · `python scripts/check_conventions.py` ·
`pnpm typecheck` · `pnpm test` · `next build`, then a live in-browser pass with the preview
tools.

That browser pass deliberately re-exercises the **gateway-unreachable error banner** — the
path T109 left unverified in a sandboxed browser and recorded as an open gap in
`apps/web/README.md`. The dashboard uses the same `apiFetch` error path, so this task
either closes that gap or reproduces it with better evidence, rather than adding a second
unverified instance of it.

## 8. Out of scope (YAGNI)

Charts and time-series, date-range pickers beyond `mtd`/`ytd`, per-user or per-trade
breakdowns, forecasting, close-rate trending, and LTV — all of these are M21/T307
(Analytics, Phase 3, Agent 3). Also excluded: caching or materialized views (three indexed
aggregates over one tenant's quotes do not warrant it yet), a `tenant.timezone` migration
(D2), and an `accepted_at` column (D5).

## 9. Forward compatibility

- **When `analytics-service` (T307) ships**, it can serve richer KPIs by consuming the
  existing `quote.*` domain events. The dashboard's contract is a single endpoint, so the
  page can be repointed without reshaping its UI.
- **When `tenant.timezone` lands**, it becomes the server-side default and `?tz=` degrades
  to an override — no breaking change.
- **When payments (T303) land**, true collected revenue becomes a distinct field alongside
  `accepted_value_minor` rather than a redefinition of it.
- **The Flutter app (T301)** consumes the same endpoint with its own device timezone; no
  server change needed.

## 10. Definition of Done

- [ ] `GET /v1/quotes/summary` implemented per §4, declared above `/{quote_id}`
- [ ] ~10 backend tests green, including tenant isolation and route ordering
- [ ] Dashboard page live against the endpoint with loading / error / empty states
- [ ] ~7 web tests green; stale T307 comment removed
- [ ] `ruff` · `mypy` · `pytest` · `check_conventions.py` · `pnpm typecheck` · `pnpm test` · `next build` all clean
- [ ] Live browser verification, including the error-banner path
- [ ] `quote-service/README.md` documents the new endpoint
- [ ] `TASKS.md` `T206` checked; `tracking/PROGRESS-TRACKER.csv` row set to `DONE`
- [ ] Agent 1 (CTO) sign-off per the cross-agent audit rule

## 11. Risks

| Risk                                                                | Mitigation                                                                        |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Route ordering silently regressed by a future edit                  | Explicit `200`-not-`422` regression test (§5.3)                                   |
| SQLite tests pass but Postgres behaves differently                  | Portable SQL only (D3); explicit `tenant_id` predicate so isolation is real (§5.2) |
| Cohort semantics misread as "revenue booked this month"             | Card labelled "Accepted Value (MTD)" + hint text stating the cohort (D4, D5)       |
| Mixed-currency tenant shown a nonsense total                        | Grouped totals, never summed (D6)                                                 |
| Contractor sees "0%" conversion when nothing has been decided       | `decided_count` drives a `—` render (§5.4)                                        |
