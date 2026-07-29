"""Parsing the model's structured output into domain types.

Structured outputs constrain the response *shape*; these tests cover the
semantics the schema can't express.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import ScopeExtractionError
from app.domain.models import TaskCategory, Trade
from app.infrastructure.claude_adapter import parse_scope

VALID = {
    "trade": "electrical",
    "summary": "Panel upgrade",
    "notes": "Permit required.",
    "tasks": [
        {
            "description": "200A electrical panel",
            "category": "material",
            "item_name": "200A main breaker panel",
            "quantity": 1,
            "unit": "each",
        },
        {
            "description": "Panel installation labor",
            "category": "labor",
            "item_name": "Panel installation",
            "quantity": 4.5,
            "unit": "hr",
        },
    ],
}


def test_parses_a_valid_payload() -> None:
    scope = parse_scope(VALID)

    assert scope.trade is Trade.ELECTRICAL
    assert len(scope.tasks) == 2
    assert scope.tasks[1].category is TaskCategory.LABOR
    assert scope.tasks[1].quantity == Decimal("4.5")


def test_fractional_quantity_stays_exact() -> None:
    """The JSON number 4.5 must not become a binary-float 4.5000000000001."""
    scope = parse_scope(VALID)
    assert scope.tasks[1].quantity == Decimal("4.5")


def test_rejects_an_unknown_trade() -> None:
    payload = {**VALID, "trade": "underwater basket weaving"}
    with pytest.raises(ScopeExtractionError):
        parse_scope(payload)


@pytest.mark.parametrize("bad_quantity", [0, -1])
def test_rejects_a_non_positive_quantity(bad_quantity: float) -> None:
    """`{"type": "number"}` accepts 0; a zero-quantity line item is not billable."""
    payload = {**VALID, "tasks": [{**VALID["tasks"][0], "quantity": bad_quantity}]}
    with pytest.raises(ScopeExtractionError, match="unusable"):
        parse_scope(payload)


def test_rejects_a_missing_field() -> None:
    incomplete = {k: v for k, v in VALID["tasks"][0].items() if k != "item_name"}
    with pytest.raises(ScopeExtractionError):
        parse_scope({**VALID, "tasks": [incomplete]})


def test_rejects_an_unknown_category() -> None:
    payload = {**VALID, "tasks": [{**VALID["tasks"][0], "category": "vibes"}]}
    with pytest.raises(ScopeExtractionError):
        parse_scope(payload)


def test_rejects_a_non_list_tasks_field() -> None:
    with pytest.raises(ScopeExtractionError, match="non-list"):
        parse_scope({**VALID, "tasks": "one panel"})


def test_missing_unit_falls_back_to_each() -> None:
    payload = {**VALID, "tasks": [{**VALID["tasks"][0], "unit": ""}]}
    assert parse_scope(payload).tasks[0].unit == "each"


def test_empty_task_list_parses_but_yields_no_tasks() -> None:
    """The use case (not the parser) decides an empty scope is an error, so
    that the message can mention the description rather than the schema."""
    scope = parse_scope({**VALID, "tasks": []})
    assert scope.tasks == ()
