# T206 — M20 Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static dashboard placeholder with a live view backed by a new `GET /v1/quotes/summary` read-model endpoint in `quote-service`, showing Quotes Today, Pending, Accepted, Accepted Value (MTD), conversion, and the 5 most recent quotes.

**Architecture:** `quote-service` gains a CQRS-style summary use case (`app/domain/summary.py` value objects + `app/application/summary.py` use cases) that runs three portable SQL aggregates over the existing `quote` table, exposed at `GET /v1/quotes/summary`. `apps/web` gains a `src/lib/dashboard.ts` data-access module and rewires `dashboard/page.tsx` from static placeholder to a `useQuery`-driven client component, following the exact pattern already used by `quotes/page.tsx`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic 2 (Python 3.12, `uv`) for the backend; Next.js 15 + TanStack Query + Zod + Vitest for the frontend.

**Spec:** [docs/modules/M20-dashboard.md](M20-dashboard.md) — read it first; this plan implements decisions D1–D6 verbatim and does not re-derive them.

## Global Constraints

- Money is integer minor units (`*_minor: int`, cents) + ISO-4217 currency. Never floats. (conventions §5)
- Rates/margins are basis points (`*_bps: int`; `10000 = 100%`). (conventions §5)
- Use `datetime.now(UTC)` — `from datetime import UTC`. Never `datetime.now(timezone.utc)` (ruff `UP017` fails CI). (conventions §6)
- Downstream services never decode JWTs; trust `x-tenant-id` / `x-user-id` headers from the gateway. (conventions §1)
- Every tenant-scoped query must be tenant-scoped explicitly — RLS is defense-in-depth, not the only guard, because the SQLite test harness has no RLS. (spec §5.2)
- Route surface under `/v1/<plural-noun>`; `/health` exposed; service reachable through the gateway. (conventions §8) — already satisfied for `quote-service`, no gateway change needed (spec §4).
- Invalid `tz` → `400`, not a silent fallback to UTC. Absent `tz` → defaults to UTC. (spec D2 + self-review addendum)
- `range_end` is always the exclusive end of the current tz-local day, equal to `day_end`. (spec §4 self-review addendum)
- Ranges are cohort-based, keyed on `created_at` — no `accepted_at` column exists. (spec D5)
- Currency totals are grouped, never summed across currencies. (spec D6)
- `ruff check` and `mypy app` must be clean; `pytest` must pass; target ≥80% coverage on domain/application logic. (conventions §7)
- `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls` must already cover `Depends`/`Query`/`Header` — it does in `quote-service/pyproject.toml`, no change needed.

---

## File Structure

```
services/quote-service/
  app/domain/summary.py          NEW   RangeBounds, CurrencyTotal, QuoteSummary (frozen dataclasses)
  app/application/summary.py     NEW   resolve_range(), summarize_quotes(), InvalidTimezoneError
  app/interface/schemas.py       EDIT  + CurrencyTotalResponse, QuoteSummaryResponse
  app/interface/routes.py        EDIT  + GET /summary (registered above /{quote_id})
  tests/test_quote_summary.py    NEW   resolve_range, summarize_quotes, tenant isolation, route ordering
  README.md                      EDIT  document the new endpoint

apps/web/
  src/lib/dashboard.ts           NEW   wire types, fetchQuoteSummary(), pure helpers
  src/lib/dashboard.test.ts      NEW   vitest unit tests
  src/lib/quotes.ts              EDIT  listQuotes() gains optional limit param
  src/lib/quotes.test.ts         EDIT  + limit-param test
  src/app/(app)/dashboard/page.tsx  EDIT  placeholder -> live client component

TASKS.md                         EDIT  check T206, refresh next-task table + rollup
tracking/PROGRESS-TRACKER.csv    EDIT  T206 row -> DONE
```

---

### Task 1: Domain value objects + pure `resolve_range`

**Files:**
- Create: `services/quote-service/app/domain/summary.py`
- Create: `services/quote-service/app/application/summary.py`
- Modify: `services/quote-service/pyproject.toml`
- Test: `services/quote-service/tests/test_quote_summary.py`

**Interfaces:**
- Produces: `RangeBounds(timezone: str, day_start: datetime, day_end: datetime, range_start: datetime, range_end: datetime)` — frozen dataclass, all datetimes UTC-aware
- Produces: `CurrencyTotal(currency: str, accepted_value_minor: int)` — frozen dataclass
- Produces: `QuoteSummary(bounds: RangeBounds, quotes_today: int, pending_count: int, accepted_count: int, decided_count: int, totals: list[CurrencyTotal])` with computed property `conversion_bps: int`
- Produces: `resolve_range(tz_name: str | None, range_key: Literal["mtd", "ytd"], *, now: datetime | None = None) -> RangeBounds`
- Produces: `InvalidTimezoneError(ValueError)`

- [ ] **Step 0: Declare the `tzdata` dependency**

`zoneinfo` needs a timezone database. Windows ships none, and slim Linux CI
containers often don't either. `tzdata` is currently present only because
`psycopg` pulls it in transitively on Windows — timezone resolution is core
behavior for this feature, so it must be declared explicitly rather than
inherited from another package's dependency tree.

In `services/quote-service/pyproject.toml`, add `tzdata` to `[project].dependencies`
(keep the existing entries, append this one):

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.2",
    "psycopg-binary>=3.2",
    "tzdata>=2026.1",
]
```

Verify: `cd services/quote-service && uv run python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Australia/Sydney'))"`
Expected: prints `Australia/Sydney` without raising `ZoneInfoNotFoundError`

- [ ] **Step 1: Write the domain value objects**

```python
# services/quote-service/app/domain/summary.py
"""Domain value objects for the quotes summary read model — framework-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RangeBounds:
    """UTC instants bounding a tz-local day and a tz-local reporting range.

    range_end always equals day_end — "to date" includes everything created
    today, and keeping the two windows aligned means a quote created minutes
    ago counts toward both quotes_today and the cohort totals.
    """

    timezone: str
    day_start: datetime
    day_end: datetime
    range_start: datetime
    range_end: datetime


@dataclass(frozen=True)
class CurrencyTotal:
    currency: str
    accepted_value_minor: int


@dataclass(frozen=True)
class QuoteSummary:
    bounds: RangeBounds
    quotes_today: int
    pending_count: int
    accepted_count: int
    decided_count: int
    totals: list[CurrencyTotal] = field(default_factory=list)

    @property
    def conversion_bps(self) -> int:
        """accepted / decided in basis points. 0 when nothing has been decided —
        callers must check decided_count before treating this as a real rate."""
        if self.decided_count == 0:
            return 0
        return round((self.accepted_count / self.decided_count) * 10000)
```

- [ ] **Step 2: Write the failing tests for `resolve_range`**

```python
# services/quote-service/tests/test_quote_summary.py
"""Tests for the quotes summary read model (T206 / M20 Dashboard)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.summary import InvalidTimezoneError, resolve_range


def test_resolve_range_defaults_to_utc_when_tz_absent():
    now = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)
    bounds = resolve_range(None, "mtd", now=now)
    assert bounds.timezone == "UTC"
    assert bounds.day_start == datetime(2026, 7, 25, 0, 0, tzinfo=UTC)
    assert bounds.day_end == datetime(2026, 7, 26, 0, 0, tzinfo=UTC)


def test_resolve_range_computes_tz_local_day_boundary():
    # 2026-07-26 05:00 UTC is 2026-07-26 15:00 in Sydney (UTC+10 in July, winter, no DST)
    now = datetime(2026, 7, 26, 5, 0, tzinfo=UTC)
    bounds = resolve_range("Australia/Sydney", "mtd", now=now)
    assert bounds.timezone == "Australia/Sydney"
    # Sydney midnight 2026-07-26 == UTC 2026-07-25 14:00
    assert bounds.day_start == datetime(2026, 7, 25, 14, 0, tzinfo=UTC)
    assert bounds.day_end == datetime(2026, 7, 26, 14, 0, tzinfo=UTC)


def test_resolve_range_handles_dst_transition_day():
    # America/New_York DST starts 2026-03-08 02:00 local (clocks spring forward to 03:00).
    # Reference instant: 2026-03-08 18:00 UTC = 13:00 EDT (already past the transition).
    now = datetime(2026, 3, 8, 18, 0, tzinfo=UTC)
    bounds = resolve_range("America/New_York", "mtd", now=now)
    # Local midnight 2026-03-08 was still EST (UTC-5) -> 05:00 UTC.
    assert bounds.day_start == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    # Local midnight 2026-03-09 is EDT (UTC-4) -> 04:00 UTC. The 23-hour DST day
    # is exactly why this boundary must be computed with zoneinfo, not a fixed offset.
    assert bounds.day_end == datetime(2026, 3, 9, 4, 0, tzinfo=UTC)


def test_resolve_range_mtd_starts_first_of_month():
    now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    bounds = resolve_range("UTC", "mtd", now=now)
    assert bounds.range_start == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    assert bounds.range_end == bounds.day_end


def test_resolve_range_ytd_starts_january_first():
    now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    bounds = resolve_range("UTC", "ytd", now=now)
    assert bounds.range_start == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_resolve_range_rejects_unknown_timezone():
    with pytest.raises(InvalidTimezoneError):
        resolve_range("Not/AZone", "mtd")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd services/quote-service && uv run pytest tests/test_quote_summary.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.application.summary'` (or `ImportError`)

- [ ] **Step 4: Implement `resolve_range`**

```python
# services/quote-service/app/application/summary.py
"""Use cases for the quotes summary read model (T206 / M20 Dashboard)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.summary import RangeBounds

RangeKey = Literal["mtd", "ytd"]


class InvalidTimezoneError(ValueError):
    """Raised when tz_name is not a recognized IANA zone."""


def resolve_range(
    tz_name: str | None,
    range_key: RangeKey,
    *,
    now: datetime | None = None,
) -> RangeBounds:
    """Compute UTC instants for the tz-local day and tz-local reporting range.

    Absent tz_name defaults to UTC. An invalid tz_name raises
    InvalidTimezoneError — silently falling back would hand the caller
    confidently wrong day boundaries with no signal anything went wrong.

    `now` is injectable so callers (tests) can pin the reference instant;
    production code omits it and gets the real current time.
    """
    resolved_name = tz_name or "UTC"
    try:
        zone = ZoneInfo(resolved_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidTimezoneError(f"unknown timezone: {resolved_name}") from exc

    reference = now if now is not None else datetime.now(UTC)
    now_local = reference.astimezone(zone)
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_local = day_start_local + timedelta(days=1)

    if range_key == "mtd":
        range_start_local = day_start_local.replace(day=1)
    else:  # ytd
        range_start_local = day_start_local.replace(month=1, day=1)

    return RangeBounds(
        timezone=resolved_name,
        day_start=day_start_local.astimezone(UTC),
        day_end=day_end_local.astimezone(UTC),
        range_start=range_start_local.astimezone(UTC),
        range_end=day_end_local.astimezone(UTC),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/quote-service && uv run pytest tests/test_quote_summary.py -v`
Expected: `6 passed`

- [ ] **Step 6: Lint and type-check**

Run: `cd services/quote-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean, no errors

- [ ] **Step 7: Commit**

```bash
git add services/quote-service/app/domain/summary.py services/quote-service/app/application/summary.py services/quote-service/tests/test_quote_summary.py services/quote-service/pyproject.toml
git commit -m "feat(T206): add resolve_range for tz-aware dashboard day/range boundaries"
```

---

### Task 2: `summarize_quotes` aggregate + tenant isolation

**Files:**
- Modify: `services/quote-service/app/application/summary.py`
- Test: `services/quote-service/tests/test_quote_summary.py`

**Interfaces:**
- Consumes: `RangeBounds` (Task 1), `QuoteSummary`, `CurrencyTotal` (Task 1)
- Consumes: `app.domain.models.QuoteModel`, `QuoteStatus` (existing)
- Consumes: `app.application.services.create_quote`, `send_quote`, `accept_quote`, `reject_quote` (existing, for test fixtures)
- Produces: `summarize_quotes(session: Session, tenant_id: uuid.UUID, bounds: RangeBounds) -> QuoteSummary`

- [ ] **Step 1: Write the failing tests**

Append to `services/quote-service/tests/test_quote_summary.py`:

```python
import uuid

from app.application import services
from app.application.summary import resolve_range, summarize_quotes
from app.domain.summary import CurrencyTotal
from app.interface.schemas import QuoteCreate


def _make_quote(db_session, tenant_id, customer_id, *, price_minor=10000):
    from app.interface.schemas import LineItemCreate

    quote, _ = services.create_quote(
        db_session,
        tenant_id,
        QuoteCreate(
            customer_id=customer_id,
            initial_line_items=[
                LineItemCreate(description="x", quantity=1, unit_price_minor=price_minor)
            ],
        ),
    )
    return quote


def test_summarize_quotes_counts_by_status(db_session, tenant_id, customer_id):
    _make_quote(db_session, tenant_id, customer_id)  # draft, excluded from pending

    sent = _make_quote(db_session, tenant_id, customer_id)
    services.send_quote(db_session, tenant_id, sent.id)

    accepted = _make_quote(db_session, tenant_id, customer_id, price_minor=50000)
    services.send_quote(db_session, tenant_id, accepted.id)
    services.accept_quote(db_session, tenant_id, accepted.id)

    rejected = _make_quote(db_session, tenant_id, customer_id)
    services.send_quote(db_session, tenant_id, rejected.id)
    services.reject_quote(db_session, tenant_id, rejected.id)

    bounds = resolve_range("UTC", "mtd")
    summary = summarize_quotes(db_session, tenant_id, bounds)

    assert summary.quotes_today == 4
    assert summary.pending_count == 1  # only the still-sent quote; draft excluded
    assert summary.accepted_count == 1
    assert summary.decided_count == 2  # accepted + rejected
    assert summary.conversion_bps == 5000  # 1/2 = 50.00%
    assert summary.totals == [CurrencyTotal("USD", 50000)]


def test_pending_count_ignores_range_and_includes_stale_sent_quotes(db_session, tenant_id, customer_id):
    from datetime import UTC, datetime, timedelta

    old_sent = _make_quote(db_session, tenant_id, customer_id)
    services.send_quote(db_session, tenant_id, old_sent.id)
    # Backdate creation so it falls outside this month's cohort but is still "pending" today.
    old_sent.created_at = datetime.now(UTC) - timedelta(days=400)
    db_session.flush()

    bounds = resolve_range("UTC", "mtd")
    summary = summarize_quotes(db_session, tenant_id, bounds)

    assert summary.pending_count == 1


def test_decided_count_zero_yields_zero_conversion_not_error(db_session, tenant_id, customer_id):
    _make_quote(db_session, tenant_id, customer_id)  # draft only, nothing decided

    bounds = resolve_range("UTC", "mtd")
    summary = summarize_quotes(db_session, tenant_id, bounds)

    assert summary.decided_count == 0
    assert summary.conversion_bps == 0


def test_summarize_quotes_enforces_tenant_isolation(db_session, tenant_id, customer_id):
    other_tenant_id = uuid.uuid4()
    _make_quote(db_session, tenant_id, customer_id)
    _make_quote(db_session, other_tenant_id, customer_id)

    bounds = resolve_range("UTC", "mtd")
    summary = summarize_quotes(db_session, tenant_id, bounds)

    assert summary.quotes_today == 1  # never 2 — the other tenant's quote must not leak in
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/quote-service && uv run pytest tests/test_quote_summary.py -v`
Expected: `FAIL` — `ImportError: cannot import name 'summarize_quotes'`

- [ ] **Step 3: Implement `summarize_quotes`**

Append to `services/quote-service/app/application/summary.py`:

```python
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import QuoteModel, QuoteStatus
from app.domain.summary import CurrencyTotal, QuoteSummary

_PENDING_STATUSES = (QuoteStatus.SENT, QuoteStatus.VIEWED)
_DECIDED_STATUSES = (QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.EXPIRED)


def summarize_quotes(session: Session, tenant_id: uuid.UUID, bounds: RangeBounds) -> QuoteSummary:
    """Aggregate quote KPIs for the dashboard.

    Every query filters on tenant_id explicitly, in addition to the RLS
    session context — the SQLite test harness has no RLS, so this predicate
    is what makes the tenant-isolation test below a genuine assertion rather
    than one that only bites on live Postgres.
    """
    quotes_today = (
        session.scalar(
            select(func.count(QuoteModel.id)).where(
                QuoteModel.tenant_id == tenant_id,
                QuoteModel.created_at >= bounds.day_start,
                QuoteModel.created_at < bounds.day_end,
            )
        )
        or 0
    )

    pending_count = (
        session.scalar(
            select(func.count(QuoteModel.id)).where(
                QuoteModel.tenant_id == tenant_id,
                QuoteModel.status.in_(_PENDING_STATUSES),
            )
        )
        or 0
    )

    cohort_rows = session.execute(
        select(
            QuoteModel.status,
            QuoteModel.currency,
            func.count(QuoteModel.id),
            func.sum(QuoteModel.total_minor),
        )
        .where(
            QuoteModel.tenant_id == tenant_id,
            QuoteModel.created_at >= bounds.range_start,
            QuoteModel.created_at < bounds.range_end,
        )
        .group_by(QuoteModel.status, QuoteModel.currency)
    ).all()

    accepted_count = 0
    decided_count = 0
    totals_by_currency: dict[str, int] = {}
    for row_status, currency, count, total in cohort_rows:
        if row_status == QuoteStatus.ACCEPTED:
            accepted_count += count
            totals_by_currency[currency] = totals_by_currency.get(currency, 0) + (total or 0)
        if row_status in _DECIDED_STATUSES:
            decided_count += count

    totals = [
        CurrencyTotal(currency=currency, accepted_value_minor=value)
        for currency, value in sorted(totals_by_currency.items())
    ]

    return QuoteSummary(
        bounds=bounds,
        quotes_today=quotes_today,
        pending_count=pending_count,
        accepted_count=accepted_count,
        decided_count=decided_count,
        totals=totals,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/quote-service && uv run pytest tests/test_quote_summary.py -v`
Expected: `11 passed`

- [ ] **Step 5: Lint and type-check**

Run: `cd services/quote-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add services/quote-service/app/application/summary.py services/quote-service/tests/test_quote_summary.py
git commit -m "feat(T206): add summarize_quotes aggregate with explicit tenant isolation"
```

---

### Task 3: `GET /v1/quotes/summary` endpoint + README

**Files:**
- Modify: `services/quote-service/app/interface/schemas.py`
- Modify: `services/quote-service/app/interface/routes.py`
- Modify: `services/quote-service/README.md`
- Test: `services/quote-service/tests/test_quote_summary.py`

**Interfaces:**
- Consumes: `resolve_range`, `summarize_quotes`, `InvalidTimezoneError` (Task 1/2)
- Consumes: `_require_tenant` (existing, `routes.py`)
- Produces: `QuoteSummaryResponse`, `CurrencyTotalResponse` (Pydantic DTOs)
- Produces: route `GET /v1/quotes/summary?tz=&range=`

- [ ] **Step 1: Write the failing route-ordering test**

This test needs no database — it inspects FastAPI's route table directly, which is what makes it a genuine regression guard for the ordering trap rather than something that only fails when Postgres happens to be reachable.

Append to `services/quote-service/tests/test_quote_summary.py`:

```python
from starlette.routing import Match

from app.main import app


def test_summary_route_is_matched_before_quote_id_route():
    """GET /{quote_id} is registered with quote_id: uuid.UUID. If /summary were
    declared after it, FastAPI would try (and fail) to parse "summary" as a
    UUID instead of reaching the summary handler. This proves route order,
    independent of any database connection."""
    from app.interface.routes import get_quotes_summary

    scope = {"type": "http", "method": "GET", "path": "/v1/quotes/summary"}
    for route in app.router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            assert route.endpoint is get_quotes_summary
            return
    pytest.fail("no route matched GET /v1/quotes/summary")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/quote-service && uv run pytest tests/test_quote_summary.py::test_summary_route_is_matched_before_quote_id_route -v`
Expected: `FAIL` — `ImportError: cannot import name 'get_quotes_summary'`

- [ ] **Step 3: Add the Pydantic response schemas**

Append to `services/quote-service/app/interface/schemas.py`:

```python
class CurrencyTotalResponse(BaseModel):
    currency: str
    accepted_value_minor: int


class QuoteSummaryResponse(BaseModel):
    timezone: str
    range: str
    range_start: datetime
    range_end: datetime
    quotes_today: int
    pending_count: int
    accepted_count: int
    decided_count: int
    conversion_bps: int
    totals: list[CurrencyTotalResponse] = Field(default_factory=list)
```

- [ ] **Step 4: Add the route, registered above `/{quote_id}`**

In `services/quote-service/app/interface/routes.py`, add these imports near the top (alongside the existing `from app.application import services` line):

```python
from typing import Literal

from app.application.summary import InvalidTimezoneError, resolve_range, summarize_quotes
from app.interface.schemas import CurrencyTotalResponse, QuoteSummaryResponse
```

Insert the new route immediately after `list_quotes` (the `@router.get("")` handler) and **before** `get_quote` (the `@router.get("/{quote_id}")` handler at line 88) — this ordering is what Step 1's test enforces:

```python
@router.get("/summary", response_model=QuoteSummaryResponse)
def get_quotes_summary(
    tz: str | None = Query(default=None, description="IANA timezone, e.g. Australia/Sydney"),
    range_key: Literal["mtd", "ytd"] = Query(default="mtd", alias="range"),
    x_tenant_id: str | None = Header(default=None),
) -> QuoteSummaryResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        bounds = resolve_range(tz, range_key)
    except InvalidTimezoneError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    with tenant_session(tenant_id) as session:
        summary = summarize_quotes(session, tenant_id, bounds)
        return QuoteSummaryResponse(
            timezone=summary.bounds.timezone,
            range=range_key,
            range_start=summary.bounds.range_start,
            range_end=summary.bounds.range_end,
            quotes_today=summary.quotes_today,
            pending_count=summary.pending_count,
            accepted_count=summary.accepted_count,
            decided_count=summary.decided_count,
            conversion_bps=summary.conversion_bps,
            totals=[
                CurrencyTotalResponse(currency=t.currency, accepted_value_minor=t.accepted_value_minor)
                for t in summary.totals
            ],
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/quote-service && uv run pytest tests/test_quote_summary.py -v`
Expected: `12 passed`

- [ ] **Step 6: Run the full quote-service suite to check for regressions**

Run: `cd services/quote-service && uv run pytest -v`
Expected: all tests pass (existing `test_quote_service.py` tests + the 12 new ones)

- [ ] **Step 7: Lint, type-check, and run the conventions guard**

Run: `cd services/quote-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean

Run: `cd "/d/TradeQuote AI" && python scripts/check_conventions.py`
Expected: passes, no violations (no `jwt` import added, ruff/mypy config present)

- [ ] **Step 8: Document the endpoint in the service README**

In `services/quote-service/README.md`, add a row to the endpoints/responsibilities section (create one if none exists) documenting:

```markdown
## Endpoints (v1)

| Method | Path                | Purpose                                                          |
| ------ | ------------------- | ----------------------------------------------------------------- |
| GET    | `/v1/quotes/summary` | Dashboard KPIs: quotes today, pending, accepted, accepted value, conversion. Query params `tz` (IANA zone, defaults UTC) and `range` (`mtd`\|`ytd`, defaults `mtd`). |
```

- [ ] **Step 9: Commit**

```bash
git add services/quote-service/app/interface/schemas.py services/quote-service/app/interface/routes.py services/quote-service/tests/test_quote_summary.py services/quote-service/README.md
git commit -m "feat(T206): expose GET /v1/quotes/summary dashboard endpoint"
```

---

### Task 4: Web pure helpers (`dashboard.ts`)

**Files:**
- Create: `apps/web/src/lib/dashboard.ts`
- Create: `apps/web/src/lib/dashboard.test.ts`

**Interfaces:**
- Produces: `interface CurrencyTotal { currency: string; accepted_value_minor: number }`
- Produces: `interface QuoteSummary { timezone: string; range: "mtd" | "ytd"; range_start: string; range_end: string; quotes_today: number; pending_count: number; accepted_count: number; decided_count: number; conversion_bps: number; totals: CurrencyTotal[] }`
- Produces: `resolveBrowserTimezone(): string`
- Produces: `formatConversion(conversionBps: number, decidedCount: number): string`
- Produces: `pickPrimaryTotal(totals: CurrencyTotal[]): CurrencyTotal | null`

- [ ] **Step 1: Write the failing tests for the pure helpers**

```typescript
// apps/web/src/lib/dashboard.test.ts
import { describe, expect, it } from "vitest";
import {
  formatConversion,
  pickPrimaryTotal,
  resolveBrowserTimezone,
  type CurrencyTotal,
} from "@/lib/dashboard";

describe("formatConversion", () => {
  it("renders an em dash when nothing has been decided", () => {
    expect(formatConversion(0, 0)).toBe("—");
  });

  it("renders a percentage with one decimal when decisions exist", () => {
    expect(formatConversion(4306, 72)).toBe("43.1%");
  });

  it("renders 0.0% when decisions exist but none were accepted", () => {
    expect(formatConversion(0, 5)).toBe("0.0%");
  });

  it("renders 100.0% when every decided quote was accepted", () => {
    expect(formatConversion(10000, 3)).toBe("100.0%");
  });
});

describe("pickPrimaryTotal", () => {
  it("returns null for an empty totals array", () => {
    expect(pickPrimaryTotal([])).toBeNull();
  });

  it("returns the first entry for a single-currency tenant", () => {
    const totals: CurrencyTotal[] = [{ currency: "USD", accepted_value_minor: 4820000 }];
    expect(pickPrimaryTotal(totals)).toEqual(totals[0]);
  });

  it("returns the first entry among multiple currencies, never summed", () => {
    const totals: CurrencyTotal[] = [
      { currency: "USD", accepted_value_minor: 100 },
      { currency: "CAD", accepted_value_minor: 200 },
    ];
    expect(pickPrimaryTotal(totals)).toEqual(totals[0]);
  });
});

describe("resolveBrowserTimezone", () => {
  it("returns a non-empty IANA zone name", () => {
    expect(resolveBrowserTimezone().length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- dashboard.test.ts`
Expected: `FAIL` — cannot find module `@/lib/dashboard`

- [ ] **Step 3: Implement the pure helpers (types + `fetchQuoteSummary` come in Task 5 — this step only needs the three functions under test)**

```typescript
// apps/web/src/lib/dashboard.ts
export interface CurrencyTotal {
  currency: string;
  accepted_value_minor: number;
}

/** IANA zone name for the current browser, e.g. "Australia/Sydney". */
export function resolveBrowserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** "—" when nothing has been decided yet — a literal 0.0% would misstate an empty pipeline. */
export function formatConversion(conversionBps: number, decidedCount: number): string {
  if (decidedCount === 0) return "—";
  return `${(conversionBps / 100).toFixed(1)}%`;
}

/** Headlines the "Accepted Value" card. Currencies are never summed (see dashboard spec D6). */
export function pickPrimaryTotal(totals: CurrencyTotal[]): CurrencyTotal | null {
  return totals[0] ?? null;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- dashboard.test.ts`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/dashboard.ts apps/web/src/lib/dashboard.test.ts
git commit -m "feat(T206): add dashboard pure helpers (conversion formatting, tz resolution)"
```

---

### Task 5: `fetchQuoteSummary` + `listQuotes` limit param

**Files:**
- Modify: `apps/web/src/lib/dashboard.ts`
- Modify: `apps/web/src/lib/dashboard.test.ts`
- Modify: `apps/web/src/lib/quotes.ts`
- Modify: `apps/web/src/lib/quotes.test.ts`

**Interfaces:**
- Consumes: `apiFetch<T>(path: string, options?: RequestOptions): Promise<T>` (existing, `api-client.ts`)
- Consumes: `CurrencyTotal` (Task 4)
- Produces: `fetchQuoteSummary(token: string, tz: string, range?: "mtd" | "ytd"): Promise<QuoteSummary>`
- Produces: `listQuotes(token: string, limit?: number): Promise<Quote[]>` — limit is optional and backward-compatible; existing callers (e.g. `quotes/page.tsx`) are unaffected

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/src/lib/dashboard.test.ts`:

```typescript
import { afterEach, vi } from "vitest";
import { fetchQuoteSummary } from "@/lib/dashboard";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(body),
    }),
  );
}

describe("fetchQuoteSummary", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests the summary endpoint with tz and range query params", async () => {
    mockFetchOnce(200, {
      timezone: "Australia/Sydney",
      range: "mtd",
      range_start: "2026-07-01T00:00:00+10:00",
      range_end: "2026-07-26T00:00:00+10:00",
      quotes_today: 4,
      pending_count: 12,
      accepted_count: 31,
      decided_count: 72,
      conversion_bps: 4306,
      totals: [],
    });

    await fetchQuoteSummary("tok", "Australia/Sydney", "mtd");

    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes/summary?tz=Australia%2FSydney&range=mtd");
  });

  it("defaults range to mtd when omitted", async () => {
    mockFetchOnce(200, {
      timezone: "UTC",
      range: "mtd",
      range_start: "2026-07-01T00:00:00Z",
      range_end: "2026-07-26T00:00:00Z",
      quotes_today: 0,
      pending_count: 0,
      accepted_count: 0,
      decided_count: 0,
      conversion_bps: 0,
      totals: [],
    });

    await fetchQuoteSummary("tok", "UTC");

    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("range=mtd");
  });

  it("propagates an ApiError when the tz is rejected by the server", async () => {
    mockFetchOnce(400, { message: "unknown timezone: Not/AZone" });
    await expect(fetchQuoteSummary("tok", "Not/AZone")).rejects.toMatchObject({ status: 400 });
  });
});
```

Append to `apps/web/src/lib/quotes.test.ts`:

```typescript
describe("listQuotes", () => {
  it("appends a limit query param when provided", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => JSON.stringify([]) }),
    );
    await listQuotes("tok", 5);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes?limit=5");
  });

  it("omits the query string when limit is not provided", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => JSON.stringify([]) }),
    );
    await listQuotes("tok");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/quotes");
    expect(call[0]).not.toContain("?");
  });
});
```

This second `describe` block needs `vi` imported — add `vi` to the existing `import { describe, expect, it } from "vitest";` line at the top of `quotes.test.ts`, making it `import { describe, expect, it, vi } from "vitest";`, and add `afterEach(() => vi.unstubAllGlobals())` inside the new `describe("listQuotes", ...)` block so these two tests don't leak a stubbed `fetch` into later test files.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- dashboard.test.ts quotes.test.ts`
Expected: `FAIL` — `fetchQuoteSummary` not exported; `listQuotes` limit test fails (no `?limit=` appended)

- [ ] **Step 3: Implement `fetchQuoteSummary` and the `QuoteSummary` type**

Append to `apps/web/src/lib/dashboard.ts`:

```typescript
import { apiFetch } from "@/lib/api-client";

export interface QuoteSummary {
  timezone: string;
  range: "mtd" | "ytd";
  range_start: string;
  range_end: string;
  quotes_today: number;
  pending_count: number;
  accepted_count: number;
  decided_count: number;
  conversion_bps: number;
  totals: CurrencyTotal[];
}

export function fetchQuoteSummary(
  token: string,
  tz: string,
  range: "mtd" | "ytd" = "mtd",
): Promise<QuoteSummary> {
  const qs = `?tz=${encodeURIComponent(tz)}&range=${range}`;
  return apiFetch<QuoteSummary>(`/v1/quotes/summary${qs}`, { token });
}
```

(Move this `import { apiFetch } from "@/lib/api-client";` to the top of the file, above the existing `export interface CurrencyTotal` from Task 4.)

- [ ] **Step 4: Implement the `listQuotes` limit param**

In `apps/web/src/lib/quotes.ts`, replace:

```typescript
export function listQuotes(token: string): Promise<Quote[]> {
  return apiFetch<Quote[] | QuoteListResponse>("/v1/quotes", { token }).then((res) =>
    Array.isArray(res) ? res : (res.items ?? []),
  );
}
```

with:

```typescript
export function listQuotes(token: string, limit?: number): Promise<Quote[]> {
  const qs = limit ? `?limit=${limit}` : "";
  return apiFetch<Quote[] | QuoteListResponse>(`/v1/quotes${qs}`, { token }).then((res) =>
    Array.isArray(res) ? res : (res.items ?? []),
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- dashboard.test.ts quotes.test.ts`
Expected: `14 passed` (11 in `dashboard.test.ts`, 2 new + existing in `quotes.test.ts`)

- [ ] **Step 6: Run the full web suite and typecheck to check for regressions**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: all pass, zero type errors

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/dashboard.ts apps/web/src/lib/dashboard.test.ts apps/web/src/lib/quotes.ts apps/web/src/lib/quotes.test.ts
git commit -m "feat(T206): add fetchQuoteSummary and listQuotes limit param"
```

---

### Task 6: Live dashboard page

**Files:**
- Modify: `apps/web/src/app/(app)/dashboard/page.tsx`

**Interfaces:**
- Consumes: `useAuthGuard()` (existing, `use-auth-guard.ts`)
- Consumes: `fetchQuoteSummary`, `formatConversion`, `pickPrimaryTotal`, `resolveBrowserTimezone` (Task 4/5)
- Consumes: `listQuotes`, `statusBadgeVariant` (existing/Task 5)
- Consumes: `formatMoney` (existing, `money.ts`)

This task has no new unit tests of its own — the logic it wires together is already covered by Tasks 4 and 5. Its correctness is verified by the manual browser pass in Task 7, per the spec's testing strategy (§7).

- [ ] **Step 1: Replace the placeholder page**

Replace the full contents of `apps/web/src/app/(app)/dashboard/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuthGuard } from "@/lib/use-auth-guard";
import {
  fetchQuoteSummary,
  formatConversion,
  pickPrimaryTotal,
  resolveBrowserTimezone,
} from "@/lib/dashboard";
import { listQuotes, statusBadgeVariant } from "@/lib/quotes";
import { formatMoney } from "@/lib/money";

interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
}

function KpiCard({ label, value, hint }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const token = useAuthGuard();
  const timezone = resolveBrowserTimezone();

  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
  } = useQuery({
    queryKey: ["quotes-summary", timezone],
    queryFn: () => fetchQuoteSummary(token as string, timezone, "mtd"),
    enabled: !!token,
  });

  const {
    data: recentQuotes,
    isLoading: recentLoading,
    isError: recentError,
  } = useQuery({
    queryKey: ["quotes", "recent"],
    queryFn: () => listQuotes(token as string, 5),
    enabled: !!token,
  });

  const primaryTotal = summary ? pickPrimaryTotal(summary.totals) : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Your quoting activity at a glance.</p>
      </div>

      {summaryError && (
        <p className="text-sm text-destructive">
          Couldn&apos;t load your quoting activity. Is the API Gateway running?
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Quotes Today"
          value={summaryLoading ? "…" : String(summary?.quotes_today ?? "—")}
        />
        <KpiCard
          label="Pending"
          value={summaryLoading ? "…" : String(summary?.pending_count ?? "—")}
          hint="Sent or viewed, awaiting a decision"
        />
        <KpiCard
          label="Accepted"
          value={summaryLoading ? "…" : String(summary?.accepted_count ?? "—")}
          hint="This month"
        />
        <KpiCard
          label="Accepted Value (MTD)"
          value={
            summaryLoading
              ? "…"
              : primaryTotal
                ? formatMoney(primaryTotal.accepted_value_minor, primaryTotal.currency)
                : formatMoney(0)
          }
          hint={
            summary
              ? `Conversion: ${formatConversion(summary.conversion_bps, summary.decided_count)}`
              : undefined
          }
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Quotes</CardTitle>
        </CardHeader>
        <CardContent>
          {recentLoading && <p className="text-sm text-muted-foreground">Loading recent quotes…</p>}
          {recentError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t load recent quotes. Is the API Gateway running?
            </p>
          )}
          {recentQuotes && recentQuotes.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No quotes yet. Once you create one, recent activity appears here.
            </p>
          )}
          {recentQuotes && recentQuotes.length > 0 && (
            <ul className="divide-y">
              {recentQuotes.map((quote) => (
                <li key={quote.id} className="flex items-center justify-between py-3">
                  <div>
                    <Link href={`/quotes/${quote.id}`} className="font-medium hover:underline">
                      {quote.number}
                    </Link>
                    <p className="text-sm text-muted-foreground">{quote.title ?? "—"}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant={statusBadgeVariant(quote.status)} className="capitalize">
                      {quote.status}
                    </Badge>
                    <span className="font-medium">
                      {formatMoney(quote.total_minor, quote.currency)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck and build**

Run: `cd apps/web && pnpm typecheck && pnpm build`
Expected: zero type errors; `next build` produces all routes including `/dashboard` with zero errors

- [ ] **Step 3: Commit**

```bash
git add "apps/web/src/app/(app)/dashboard/page.tsx"
git commit -m "feat(T206): wire dashboard page to live quote summary + recent quotes"
```

---

### Task 7: Full gate, live verification, and tracker bookkeeping

**Files:**
- Modify: `TASKS.md`
- Modify: `tracking/PROGRESS-TRACKER.csv`

- [ ] **Step 1: Run every gate**

```bash
cd services/quote-service && uv run ruff check app tests && uv run mypy app && uv run pytest -v
cd "/d/TradeQuote AI" && python scripts/check_conventions.py
cd apps/web && pnpm typecheck && pnpm test && pnpm build
```

Expected: every command exits 0.

- [ ] **Step 2: Live browser verification**

Using the project's preview tooling: start the API Gateway, `quote-service`, and the web app; log in; navigate to `/dashboard`. Confirm:

- All four KPI cards render real numbers (not `"—"` placeholders) once loaded
- "Accepted Value (MTD)" shows a formatted currency amount and a "Conversion: N.N%" hint
- Recent Quotes lists up to 5 quotes, each linking to `/quotes/[id]`
- With the API Gateway stopped, the dashboard shows the "Couldn't load your quoting activity" error banner rather than hanging — this is the same error path left unverified in a sandboxed browser after T109 (`apps/web/README.md`'s Definition of Done gap); confirming it here either closes that gap or reproduces it with concrete evidence, rather than adding a second unverified instance

- [ ] **Step 3: Update `TASKS.md`**

Change line 46 from:

```markdown
- [ ] `T206` **[A2]** M20 Dashboard: quotes today/pending/accepted/revenue/conversion — _deps: T106_
```

to:

```markdown
- [x] `T206` **[A2]** M20 Dashboard: quotes today/pending/accepted/revenue/conversion — _deps: T106_ ✅ `GET /v1/quotes/summary` read model + live dashboard page; see [M20 spec](docs/modules/M20-dashboard.md)
```

Update the Phase 2 rollup row (around line 100) from `Phase 2   | 7      | 1      | 0           | 14%     |` to `Phase 2   | 7      | 2      | 0           | 29%     |`, and the Total row from `**Total** | **35** | **19** | **0**       | **54%** |` to `**Total** | **35** | **20** | **0**       | **57%** |`.

Remove the `T206` row from the "Check for Next Task" table (it's no longer blocked-on-nothing/ready — it's done).

- [ ] **Step 4: Update `tracking/PROGRESS-TRACKER.csv`**

Change the `T206` row from:

```
T206,M20,Dashboard,Phase 2,Agent 2,Sonnet 5,P1,NOT_STARTED,,,T106,,
```

to (using the actual date you complete this task for both Start and End Date):

```
T206,M20,Dashboard,Phase 2,Agent 2,Sonnet 5,P1,DONE,2026-07-25,2026-07-25,T106,Architecture;API;Database;Code Review;QA,GET /v1/quotes/summary read model (quote-service) + live dashboard page (apps/web); tz-aware day/range boundaries; tenant-isolation + route-ordering tests
```

- [ ] **Step 5: Commit**

```bash
git add TASKS.md tracking/PROGRESS-TRACKER.csv
git commit -m "docs(T206): mark M20 Dashboard done, refresh rollup and tracker"
```

- [ ] **Step 6: Note for Agent 1 sign-off**

Per `AGENTS.md`'s cross-agent audit rule, Agent 1 (CTO) reviews every completed task from another agent before it counts as fully signed off. This plan's Definition of Done (spec §10) is satisfied by Tasks 1–7, but the CTO audit itself is outside this plan's scope — flag the branch for review rather than merging directly to `main`.

---

## Self-Review Notes

**Spec coverage:** D1 (quote-service aggregation) → Tasks 1–3. D2 (client tz, invalid → 400) → Task 1 `resolve_range` + Task 3 route. D3 (Python boundary math, portable SQL) → Task 1 + Task 2. D4 (Accepted Value naming) → Task 3 schema field name + Task 6 card label. D5 (cohort semantics on `created_at`) → Task 2 aggregate query. D6 (currency totals never summed) → Task 2 `totals` list + Task 4 `pickPrimaryTotal`. §3 KPI definitions (pending excludes draft, ignores range) → Task 2 tests. §5.3 route-ordering trap → Task 3. §5.4 error handling → Task 3 (400/422/200-with-zeros) + Task 6 (error banner). §7 testing strategy → Tasks 1–5 unit tests + Task 7 live pass. §10 DoD → Task 7.

**Placeholder scan:** no TBD/TODO; every step has complete code or an exact command with expected output.

**Type consistency:** `RangeBounds`, `CurrencyTotal`, `QuoteSummary` (Task 1) are consumed unchanged in Task 2 and Task 3. `resolve_range(tz_name, range_key, *, now=None)` signature is identical in its Task 1 definition and every Task 1/2/3 call site. `fetchQuoteSummary(token, tz, range?)` and `QuoteSummary` (Task 5) match the response shape `QuoteSummaryResponse` produces in Task 3 field-for-field. `listQuotes(token, limit?)` signature (Task 5) matches its Task 6 call site (`listQuotes(token as string, 5)`).
