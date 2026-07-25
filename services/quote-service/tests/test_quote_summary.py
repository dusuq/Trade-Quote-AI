"""Tests for the quotes summary read model (T206 / M20 Dashboard)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application import services
from app.application.summary import (
    InvalidTimezoneError,
    UnsupportedRangeError,
    resolve_range,
    summarize_quotes,
)
from app.domain.summary import CurrencyTotal
from app.interface.schemas import LineItemCreate, QuoteCreate


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
    # Reference instant: 2026-03-08 18:00 UTC = 14:00 EDT (already past the transition).
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


@pytest.mark.parametrize("tz_name", ["/etc/passwd", "..", "../../etc/passwd"])
def test_resolve_range_rejects_malformed_timezone_keys(tz_name: str):
    """ZoneInfo raises a bare ValueError (not ZoneInfoNotFoundError) for absolute
    and non-normalized keys. Catching only ZoneInfoNotFoundError let these escape
    as an unhandled 500; spec §5.4 contracts 400 for every invalid zone."""
    with pytest.raises(InvalidTimezoneError):
        resolve_range(tz_name, "mtd")


@pytest.mark.parametrize("tz_name", ["", "   ", "\t"])
def test_resolve_range_rejects_blank_timezone_but_not_absent_one(tz_name: str):
    """Absent vs invalid are deliberately different (spec D2): None means "no
    preference, use UTC", while ?tz= is a caller who meant to name a zone and
    failed. Blank must not silently degrade to UTC."""
    with pytest.raises(InvalidTimezoneError):
        resolve_range(tz_name, "mtd")

    assert resolve_range(None, "mtd").timezone == "UTC"


def test_resolve_range_rejects_unrecognized_range_key():
    """Guards a future RangeKey member added to the Literal without a branch in
    resolve_range, which would otherwise be served YTD figures under its label."""
    with pytest.raises(UnsupportedRangeError):
        resolve_range("UTC", "qtd")  # type: ignore[arg-type]


def _make_quote(db_session, tenant_id, customer_id, *, price_minor=10000, currency="USD"):
    quote, _ = services.create_quote(
        db_session,
        tenant_id,
        QuoteCreate(
            customer_id=customer_id,
            currency=currency,
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


def test_summary_route_is_matched_before_quote_id_route(client, auth_header):
    """GET /{quote_id} is registered with quote_id: uuid.UUID. If /summary were
    declared after it, "summary" would match the generic path segment there
    instead, and FastAPI would fail to parse it as a UUID before the handler
    ever runs, yielding 422 without ever reaching get_quotes_summary.

    Why the empty-tz request is the assertion that proves ordering, and must not
    be "simplified" back to a bare unauthenticated GET: with a valid tenant
    header, ?tz= reaches get_quotes_summary and is rejected 400 by resolve_range
    (it touches no database, so no session seam is needed). Under mis-ordering
    the request never reaches any handler — path-param validation fails first
    and returns 422. 400-vs-422 therefore depends only on which route matched.

    The 401 case below is a weaker companion: it holds only while _require_tenant
    is a plain function call. If it were ever refactored into a FastAPI Depends,
    a mis-registered route would 401 too and this test would stop catching the
    regression it exists for — hence the auth-independent assertion above it."""
    ordering = client.get("/v1/quotes/summary", params={"tz": ""}, headers=auth_header)
    assert ordering.status_code == 400, "422 means /{quote_id} matched /summary first"

    unauthenticated = client.get("/v1/quotes/summary")
    assert unauthenticated.status_code == 401


def test_summary_rejects_empty_tz_instead_of_defaulting_to_utc(client, auth_header):
    """An empty ?tz= query string arrives at FastAPI as "" (not None), which must
    not be treated as "absent, use UTC" (spec D2). resolve_range owns this rule
    now — the route no longer special-cases it — so this asserts the behavior end
    to end rather than the removed guard."""
    response = client.get("/v1/quotes/summary", params={"tz": ""}, headers=auth_header)
    assert response.status_code == 400


@pytest.mark.parametrize("tz_name", ["Not/AZone", "/etc/passwd", "..", "../../etc/passwd"])
def test_summary_route_returns_400_not_500_for_any_invalid_tz(client, auth_header, tz_name: str):
    """Spec §5.4 contracts 400 for an unknown/invalid zone. Absolute and
    non-normalized keys used to escape resolve_range as a bare ValueError and
    surface as an unhandled 500."""
    response = client.get("/v1/quotes/summary", params={"tz": tz_name}, headers=auth_header)
    assert response.status_code == 400


def test_summary_endpoint_returns_the_full_contracted_body(
    client, api_session, auth_header, tenant_id, customer_id
):
    """Pins every field name and value of the 200 response body.

    These names are the exact contract apps/web/src/lib/dashboard.ts is written
    against, and nothing else executable pins them: without this test the DTO
    could be renamed or a field dropped with the whole suite still green.
    """
    accepted_usd = _make_quote(api_session, tenant_id, customer_id, price_minor=50000)
    services.send_quote(api_session, tenant_id, accepted_usd.id)
    services.accept_quote(api_session, tenant_id, accepted_usd.id)

    accepted_aud = _make_quote(
        api_session, tenant_id, customer_id, price_minor=20000, currency="AUD"
    )
    services.send_quote(api_session, tenant_id, accepted_aud.id)
    services.accept_quote(api_session, tenant_id, accepted_aud.id)

    rejected = _make_quote(api_session, tenant_id, customer_id)
    services.send_quote(api_session, tenant_id, rejected.id)
    services.reject_quote(api_session, tenant_id, rejected.id)

    sent = _make_quote(api_session, tenant_id, customer_id)
    services.send_quote(api_session, tenant_id, sent.id)

    _make_quote(api_session, tenant_id, customer_id)  # draft

    # A foreign tenant's accepted quote must never appear in these figures.
    _make_quote(api_session, uuid.uuid4(), customer_id, price_minor=999999)
    api_session.flush()

    response = client.get("/v1/quotes/summary", params={"tz": "UTC"}, headers=auth_header)
    assert response.status_code == 200
    body = response.json()

    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    assert body["timezone"] == "UTC"
    assert body["range"] == "mtd"
    assert datetime.fromisoformat(body["range_start"]) == day_start.replace(day=1)
    assert datetime.fromisoformat(body["range_end"]) == day_start + timedelta(days=1)
    assert body["quotes_today"] == 5
    assert body["pending_count"] == 1  # the still-sent quote; draft excluded
    assert body["accepted_count"] == 2
    assert body["decided_count"] == 3  # 2 accepted + 1 rejected
    assert body["conversion_bps"] == 6667  # round(2/3 * 10000)
    assert body["totals"] == [
        {"currency": "AUD", "accepted_value_minor": 20000},
        {"currency": "USD", "accepted_value_minor": 50000},
    ]
    assert set(body) == {
        "timezone",
        "range",
        "range_start",
        "range_end",
        "quotes_today",
        "pending_count",
        "accepted_count",
        "decided_count",
        "conversion_bps",
        "totals",
    }
