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


import uuid

from app.application import services
from app.application.summary import summarize_quotes
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
