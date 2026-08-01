"""Parsing the sales-coach model's structured output into domain types."""

from __future__ import annotations

import pytest

from app.domain.errors import SalesCoachError
from app.domain.models import SalesSuggestionKind
from app.infrastructure.claude_sales_coach_adapter import parse_sales_coach

VALID = {
    "summary": "One strong cross-sell opportunity given the panel upgrade.",
    "suggestions": [
        {
            "kind": "cross_sell",
            "item_name": "Whole-home surge protector",
            "description": "Panel-mounted surge protection for the whole house.",
            "reasoning": "Panel upgrades are the natural moment to add this.",
            "talking_point": "While we're in the panel, want me to add surge protection?",
            "estimated_price_minor": 25_000,
        },
        {
            "kind": "warranty",
            "item_name": "5-year extended workmanship warranty",
            "description": "Extends coverage beyond the standard 1-year warranty.",
            "reasoning": "Customers rarely decline a warranty offered at time of install.",
            "talking_point": "Want to extend your warranty to 5 years for extra peace of mind?",
            "estimated_price_minor": None,
        },
    ],
}


def test_parses_a_valid_payload() -> None:
    result = parse_sales_coach(VALID, model_id="claude-sonnet-5", tokens_used=800)

    assert result.summary == VALID["summary"]
    assert len(result.suggestions) == 2
    assert result.model_id == "claude-sonnet-5"
    assert result.tokens_used == 800


def test_kind_parses_to_the_enum() -> None:
    result = parse_sales_coach(VALID, model_id="m", tokens_used=1)
    assert result.suggestions[0].kind is SalesSuggestionKind.CROSS_SELL
    assert result.suggestions[1].kind is SalesSuggestionKind.WARRANTY


def test_estimated_price_minor_is_carried_through_when_present() -> None:
    result = parse_sales_coach(VALID, model_id="m", tokens_used=1)
    assert result.suggestions[0].estimated_price_minor == 25_000


def test_estimated_price_minor_stays_none_when_absent() -> None:
    result = parse_sales_coach(VALID, model_id="m", tokens_used=1)
    assert result.suggestions[1].estimated_price_minor is None


def test_empty_suggestions_list_parses_but_yields_nothing() -> None:
    """The model itself decides an empty list is fine here — unlike vision
    detection or OCR extraction, "nothing worth suggesting" is a valid
    sales-coach answer, so the use case doesn't reject it either."""
    result = parse_sales_coach({**VALID, "suggestions": []}, model_id="m", tokens_used=1)
    assert result.suggestions == ()


def test_rejects_an_unknown_kind() -> None:
    payload = {**VALID, "suggestions": [{**VALID["suggestions"][0], "kind": "discount"}]}
    with pytest.raises(SalesCoachError):
        parse_sales_coach(payload, model_id="m", tokens_used=1)


def test_rejects_a_missing_field() -> None:
    incomplete = {k: v for k, v in VALID["suggestions"][0].items() if k != "talking_point"}
    with pytest.raises(SalesCoachError):
        parse_sales_coach({**VALID, "suggestions": [incomplete]}, model_id="m", tokens_used=1)


def test_rejects_a_non_list_suggestions_field() -> None:
    with pytest.raises(SalesCoachError, match="non-list"):
        parse_sales_coach({**VALID, "suggestions": "one surge protector"}, model_id="m", tokens_used=1)


def test_missing_summary_defaults_to_empty_string() -> None:
    payload = {"suggestions": []}
    result = parse_sales_coach(payload, model_id="m", tokens_used=1)
    assert result.summary == ""
