"""Parsing the vision model's structured output into domain types."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import EquipmentDetectionError
from app.domain.models import EquipmentCondition, TaskCategory, Trade
from app.infrastructure.claude_vision_adapter import parse_detection

VALID = {
    "trade": "electrical",
    "summary": "200A panel showing wear",
    "notes": "Main lugs show corrosion.",
    "equipment": [
        {
            "name": "200A Square D QO load center",
            "category": "material",
            "condition": "worn",
            "quantity": 1,
            "unit": "each",
        },
        {
            "name": "Remove and replace panel",
            "category": "labor",
            "condition": "unknown",
            "quantity": 4.5,
            "unit": "hr",
        },
    ],
}


def test_parses_a_valid_payload() -> None:
    detection = parse_detection(VALID)

    assert detection.trade is Trade.ELECTRICAL
    assert len(detection.equipment) == 2
    assert detection.equipment[0].condition is EquipmentCondition.WORN
    assert detection.equipment[1].quantity == Decimal("4.5")


def test_fractional_quantity_stays_exact() -> None:
    detection = parse_detection(VALID)
    assert detection.equipment[1].quantity == Decimal("4.5")


def test_rejects_an_unknown_trade() -> None:
    payload = {**VALID, "trade": "underwater basket weaving"}
    with pytest.raises(EquipmentDetectionError):
        parse_detection(payload)


def test_rejects_an_unknown_condition() -> None:
    payload = {**VALID, "equipment": [{**VALID["equipment"][0], "condition": "pristine"}]}
    with pytest.raises(EquipmentDetectionError):
        parse_detection(payload)


@pytest.mark.parametrize("bad_quantity", [0, -1])
def test_rejects_a_non_positive_quantity(bad_quantity: float) -> None:
    payload = {**VALID, "equipment": [{**VALID["equipment"][0], "quantity": bad_quantity}]}
    with pytest.raises(EquipmentDetectionError, match="unusable"):
        parse_detection(payload)


def test_rejects_a_missing_field() -> None:
    incomplete = {k: v for k, v in VALID["equipment"][0].items() if k != "name"}
    with pytest.raises(EquipmentDetectionError):
        parse_detection({**VALID, "equipment": [incomplete]})


def test_rejects_an_unknown_category() -> None:
    payload = {**VALID, "equipment": [{**VALID["equipment"][0], "category": "vibes"}]}
    with pytest.raises(EquipmentDetectionError):
        parse_detection(payload)


def test_rejects_a_non_list_equipment_field() -> None:
    with pytest.raises(EquipmentDetectionError, match="non-list"):
        parse_detection({**VALID, "equipment": "one panel"})


def test_missing_unit_falls_back_to_each() -> None:
    payload = {**VALID, "equipment": [{**VALID["equipment"][0], "unit": ""}]}
    assert parse_detection(payload).equipment[0].unit == "each"


def test_empty_equipment_list_parses_but_yields_nothing() -> None:
    """The use case (not the parser) decides an empty detection is an error —
    same split as `parse_scope`/`test_scope_extraction`."""
    detection = parse_detection({**VALID, "equipment": []})
    assert detection.equipment == ()


def test_category_material_parses() -> None:
    payload = {**VALID, "equipment": [{**VALID["equipment"][0], "category": "material"}]}
    assert parse_detection(payload).equipment[0].category is TaskCategory.MATERIAL
