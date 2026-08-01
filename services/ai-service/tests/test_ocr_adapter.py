"""Parsing the document-extraction model's structured output into domain types."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import DocumentExtractionError
from app.domain.models import DocumentKind, TaskCategory, Trade
from app.infrastructure.claude_ocr_adapter import parse_extraction

VALID = {
    "document_kind": "invoice",
    "trade": "plumbing",
    "summary": "Copper pipe and fittings restock",
    "vendor_name": "Acme Supply Co.",
    "document_date": "07/15/2026",
    "reference_number": "INV-4471",
    "notes": "",
    "line_items": [
        {
            "description": "3/4in copper pipe, 10ft length",
            "category": "material",
            "item_name": "3/4in copper pipe",
            "quantity": 10,
            "unit": "ft",
            "unit_cost_minor": 450,
        },
        {
            "description": "Delivery fee",
            "category": "labor",
            "item_name": "delivery fee",
            "quantity": 1,
            "unit": "each",
            "unit_cost_minor": None,
        },
    ],
}


def test_parses_a_valid_payload() -> None:
    extraction = parse_extraction(VALID)

    assert extraction.document_kind is DocumentKind.INVOICE
    assert extraction.trade is Trade.PLUMBING
    assert extraction.vendor_name == "Acme Supply Co."
    assert extraction.reference_number == "INV-4471"
    assert len(extraction.line_items) == 2


def test_unit_cost_minor_is_carried_through_when_present() -> None:
    extraction = parse_extraction(VALID)
    assert extraction.line_items[0].unit_cost_minor == 450


def test_unit_cost_minor_stays_none_when_the_document_has_no_price() -> None:
    extraction = parse_extraction(VALID)
    assert extraction.line_items[1].unit_cost_minor is None


def test_fractional_quantity_stays_exact() -> None:
    payload = {**VALID, "line_items": [{**VALID["line_items"][0], "quantity": 4.5}]}
    extraction = parse_extraction(payload)
    assert extraction.line_items[0].quantity == Decimal("4.5")


def test_blueprint_and_handwritten_kinds_parse() -> None:
    for kind in ("blueprint", "handwritten"):
        extraction = parse_extraction({**VALID, "document_kind": kind})
        assert extraction.document_kind.value == kind


def test_rejects_an_unknown_document_kind() -> None:
    payload = {**VALID, "document_kind": "napkin"}
    with pytest.raises(DocumentExtractionError):
        parse_extraction(payload)


def test_rejects_an_unknown_trade() -> None:
    payload = {**VALID, "trade": "underwater basket weaving"}
    with pytest.raises(DocumentExtractionError):
        parse_extraction(payload)


@pytest.mark.parametrize("bad_quantity", [0, -1])
def test_rejects_a_non_positive_quantity(bad_quantity: float) -> None:
    payload = {**VALID, "line_items": [{**VALID["line_items"][0], "quantity": bad_quantity}]}
    with pytest.raises(DocumentExtractionError, match="unusable"):
        parse_extraction(payload)


def test_rejects_a_missing_field() -> None:
    incomplete = {k: v for k, v in VALID["line_items"][0].items() if k != "description"}
    with pytest.raises(DocumentExtractionError):
        parse_extraction({**VALID, "line_items": [incomplete]})


def test_rejects_an_unknown_category() -> None:
    payload = {**VALID, "line_items": [{**VALID["line_items"][0], "category": "vibes"}]}
    with pytest.raises(DocumentExtractionError):
        parse_extraction(payload)


def test_rejects_a_non_list_line_items_field() -> None:
    with pytest.raises(DocumentExtractionError, match="non-list"):
        parse_extraction({**VALID, "line_items": "one pipe"})


def test_missing_unit_falls_back_to_each() -> None:
    payload = {**VALID, "line_items": [{**VALID["line_items"][0], "unit": ""}]}
    assert parse_extraction(payload).line_items[0].unit == "each"


def test_empty_line_items_list_parses_but_yields_nothing() -> None:
    """The use case (not the parser) decides an empty extraction is an
    error — same split as `parse_detection`/`test_vision_adapter`."""
    extraction = parse_extraction({**VALID, "line_items": []})
    assert extraction.line_items == ()


def test_category_equipment_parses() -> None:
    payload = {**VALID, "line_items": [{**VALID["line_items"][0], "category": "equipment"}]}
    assert parse_extraction(payload).line_items[0].category is TaskCategory.EQUIPMENT


def test_missing_optional_header_fields_default_to_empty_string() -> None:
    minimal = {
        "document_kind": "blueprint",
        "trade": "electrical",
        "line_items": [VALID["line_items"][0]],
    }
    extraction = parse_extraction(minimal)
    assert extraction.vendor_name == ""
    assert extraction.document_date == ""
    assert extraction.reference_number == ""
    assert extraction.notes == ""
