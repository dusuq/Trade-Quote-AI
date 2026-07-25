"""Use cases for the quotes summary read model (T206 / M20 Dashboard)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import QuoteModel, QuoteStatus
from app.domain.summary import CurrencyTotal, QuoteSummary, RangeBounds

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
