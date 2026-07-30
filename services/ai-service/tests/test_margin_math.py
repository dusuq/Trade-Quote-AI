"""Pure margin/markup arithmetic — no LLM, no I/O (M16 Key Design Decision #2)."""

from __future__ import annotations

from decimal import Decimal

from app.application.margin import (
    LOW_MARGIN_THRESHOLD_BPS,
    compute_margin,
    line_cost_minor,
    margin_bps,
    markup_bps,
)
from tests.fakes import make_line_item, make_snapshot


def test_zero_markup_is_zero_margin() -> None:
    # revenue == cost → nothing left over.
    assert margin_bps(revenue_minor=10_000, cost_minor=10_000) == 0


def test_hundred_percent_markup_is_fifty_percent_margin() -> None:
    # price = 2 × cost → margin is half the price. 10000 bps markup ⇒ 5000 bps margin.
    assert margin_bps(revenue_minor=20_000, cost_minor=10_000) == 5_000
    assert markup_bps(revenue_minor=20_000, cost_minor=10_000) == 10_000


def test_no_revenue_and_no_cost_are_zero_not_crash() -> None:
    assert margin_bps(0, 0) == 0
    assert markup_bps(10_000, 0) == 0  # cannot mark up nothing


def test_line_cost_uses_decimal_quantity_and_rounds_half_up() -> None:
    item = make_line_item(unit_cost_minor=333, quantity="3", unit_price_minor=333)
    assert line_cost_minor(item) == 999
    # 2.5 × 333 = 832.5 → 833 (half up), never a fractional cent.
    fractional = make_line_item(unit_cost_minor=333, quantity="2.5", unit_price_minor=333)
    assert line_cost_minor(fractional) == 833
    assert isinstance(line_cost_minor(fractional), int)


def test_low_margin_items_flagged_below_threshold() -> None:
    healthy = make_line_item(  # 50% margin
        unit_cost_minor=5_000, unit_price_minor=10_000, quantity="1"
    )
    thin = make_line_item(  # ~9% margin, below the 20% floor
        unit_cost_minor=10_000, unit_price_minor=11_000, quantity="1"
    )
    quote = make_snapshot(line_items=(healthy, thin))

    margin = compute_margin(quote, "check the thin one")

    assert thin.id in margin.low_margin_item_ids
    assert healthy.id not in margin.low_margin_item_ids
    assert LOW_MARGIN_THRESHOLD_BPS == 2_000


def test_compute_margin_totals_match_the_snapshot() -> None:
    item = make_line_item(unit_cost_minor=10_000, unit_price_minor=20_000, quantity="1")
    quote = make_snapshot(line_items=(item,))

    margin = compute_margin(quote, "ok")

    assert margin.total_cost_minor == 10_000
    assert margin.total_revenue_minor == quote.subtotal_minor == 20_000
    assert margin.gross_margin_bps == 5_000
    assert margin.average_markup_bps == 10_000
    assert margin.recommendation == "ok"


def test_line_cost_quantity_is_decimal_not_float() -> None:
    item = make_line_item(quantity="1.1", unit_cost_minor=100)
    assert item.quantity == Decimal("1.1")
    assert line_cost_minor(item) == 110
