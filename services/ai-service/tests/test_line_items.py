"""Line-item mapping and the money conventions (§5).

These are the tests that keep a wrong price out of a customer's quote.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.line_items import (
    DEFAULT_MARKUP_BPS,
    build_line_items,
    normalize_quantity,
    to_line_item,
)
from app.domain.models import MatchedTask, TaskCategory
from tests.fakes import make_match, make_task


def test_quantity_never_passes_through_binary_float() -> None:
    """`Decimal(0.1)` is 0.1000000000000000055...; `Decimal("0.1")` is exact.

    A quantity multiplies a money value downstream, so the difference is a
    real pricing error rather than a cosmetic one.
    """
    assert normalize_quantity(0.1) == Decimal("0.1")
    assert normalize_quantity("2.5") == Decimal("2.5")
    assert normalize_quantity(3) == Decimal(3)


@pytest.mark.parametrize("bad", [0, -1, "0", "-2.5"])
def test_quantity_must_be_positive(bad: object) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        normalize_quantity(bad)


@pytest.mark.parametrize("bad", ["abc", None, "NaN", "Infinity"])
def test_quantity_rejects_non_numbers(bad: object) -> None:
    with pytest.raises(ValueError):
        normalize_quantity(bad)


def test_matched_task_uses_pricebook_cost_and_kind() -> None:
    """The catalog is authoritative about what an item is; the model just found it."""
    matched = MatchedTask(
        task=make_task("200A panel", category=TaskCategory.EQUIPMENT, unit="box"),
        match=make_match(unit_cost_minor=85_000, unit="each", kind="material"),
    )

    item = to_line_item(matched, default_markup_bps=DEFAULT_MARKUP_BPS)

    assert item.unit_cost_minor == 85_000
    assert item.kind == "material"  # pricebook's kind, not the LLM's "equipment"
    assert item.unit == "each"  # pricebook's unit, not the LLM's "box"
    assert item.pricebook_item_id is not None


def test_pricebook_markup_wins_over_the_request_default() -> None:
    """A tenant who priced this item at 15% meant 15%, not the blanket 30%."""
    matched = MatchedTask(task=make_task(), match=make_match(markup_bps=1500))

    item = to_line_item(matched, default_markup_bps=DEFAULT_MARKUP_BPS)

    assert item.markup_bps == 1500


def test_request_default_applies_when_the_pricebook_has_no_markup() -> None:
    matched = MatchedTask(task=make_task(), match=make_match(markup_bps=0))

    item = to_line_item(matched, default_markup_bps=2500)

    assert item.markup_bps == 2500


def test_unmatched_task_survives_as_a_zero_cost_line() -> None:
    """Scope the customer described must never be silently dropped."""
    matched = MatchedTask(task=make_task("bespoke widget"), match=None)

    item = to_line_item(matched, default_markup_bps=DEFAULT_MARKUP_BPS)

    assert item.unit_cost_minor == 0
    assert item.pricebook_item_id is None
    assert item.description == "bespoke widget"
    # Markup is 0, not the default: marking up nothing is still nothing, and a
    # non-zero markup here would imply we priced something we didn't.
    assert item.markup_bps == 0


def test_line_items_never_carry_a_price() -> None:
    """quote-service derives `unit_price_minor`; duplicating that arithmetic
    here would create a second source of truth that can drift."""
    item = to_line_item(MatchedTask(task=make_task(), match=make_match()))

    assert not hasattr(item, "unit_price_minor")


def test_build_line_items_preserves_order_and_numbers_them() -> None:
    matched = [
        MatchedTask(task=make_task("first"), match=make_match()),
        MatchedTask(task=make_task("second"), match=None),
        MatchedTask(task=make_task("third"), match=make_match()),
    ]

    items = build_line_items(matched)

    assert [item.description for item in items] == ["first", "second", "third"]
    assert [item.sort_order for item in items] == [0, 1, 2]


def test_negative_markup_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        to_line_item(MatchedTask(task=make_task(), match=make_match()), default_markup_bps=-1)


def test_money_stays_an_integer_end_to_end() -> None:
    """Conventions §5: money is integer minor units, never a float."""
    items = build_line_items(
        [MatchedTask(task=make_task(quantity="2.5"), match=make_match(unit_cost_minor=1_234))]
    )

    assert isinstance(items[0].unit_cost_minor, int)
    assert isinstance(items[0].markup_bps, int)
    assert isinstance(items[0].quantity, Decimal)
