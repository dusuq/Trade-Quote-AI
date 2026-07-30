"""Copilot prompt schemas + the pure parse_* functions (no SDK, no network)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.domain.errors import CopilotAnalysisError
from app.domain.models import Trade
from app.infrastructure.copilot_claude_adapter import (
    parse_missing_items,
    parse_pricing_suggestions,
    parse_rewrite,
)
from app.infrastructure.prompts import copilot_missing, copilot_pricing, copilot_rewrite
from tests.fakes import make_line_item, make_match, make_snapshot


def _assert_structured_output_valid(schema: dict[str, Any]) -> None:
    """The API rejects object schemas unless every property is required and
    additionalProperties is false. Enforce that recursively."""
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        assert schema.get("additionalProperties") is False
        assert set(schema.get("required", [])) == set(props)
        for child in props.values():
            _assert_structured_output_valid(child)
    if schema.get("type") == "array":
        _assert_structured_output_valid(schema["items"])


def test_all_schemas_are_valid_structured_outputs() -> None:
    _assert_structured_output_valid(copilot_pricing.PRICING_ANALYSIS_SCHEMA)
    _assert_structured_output_valid(copilot_missing.MISSING_ITEMS_SCHEMA)
    _assert_structured_output_valid(copilot_rewrite.REWRITE_SCHEMA)


def test_missing_prompt_interpolates_trade() -> None:
    prompt = copilot_missing.build_system_prompt("plumbing")
    assert "plumbing estimator" in prompt
    assert "{trade}" not in prompt


def test_rewrite_prompt_quotes_context_as_data() -> None:
    prompt = copilot_rewrite.build_system_prompt("professional", "electrical panel")
    assert "professional" in prompt
    assert "electrical panel" in prompt


# ── parse_pricing_suggestions ─────────────────────────────────────────────────


def test_parse_pricing_aligns_and_copies_current_values() -> None:
    line1 = make_line_item(description="panel", unit_cost_minor=80_000, markup_bps=3000)
    line2 = make_line_item(description="labor", unit_cost_minor=6_000, markup_bps=5000)
    quote = make_snapshot(line_items=(line1, line2))
    matches = {line1.id: make_match(unit_cost_minor=77_000)}
    payload = {
        "suggestions": [
            {"line_item_id": str(line1.id), "suggested_markup_bps": 3500, "reasoning": "bump it"},
            # line2 intentionally absent → suggestion still emitted, null markup.
        ],
        "margin_recommendation": "overall fine",
    }

    suggestions, recommendation = parse_pricing_suggestions(payload, quote, matches)

    assert len(suggestions) == 2  # one per line, in order
    assert suggestions[0].line_item_id == line1.id
    assert suggestions[0].current_markup_bps == 3000
    assert suggestions[0].suggested_markup_bps == 3500
    assert suggestions[0].pricebook_unit_cost_minor == 77_000
    assert suggestions[1].suggested_markup_bps is None
    assert suggestions[1].pricebook_unit_cost_minor is None
    assert recommendation == "overall fine"


def test_parse_pricing_rejects_non_list_suggestions() -> None:
    quote = make_snapshot()
    with pytest.raises(CopilotAnalysisError):
        parse_pricing_suggestions({"suggestions": "nope"}, quote, {})


# ── parse_missing_items ───────────────────────────────────────────────────────


def test_parse_missing_items_happy() -> None:
    payload = {
        "trade": "electrical",
        "completeness_score": 72,
        "summary": "add a permit",
        "missing": [
            {
                "description": "Permit",
                "category": "labor",
                "item_name": "electrical permit",
                "estimated_quantity": 1,
                "unit": "each",
                "reasoning": "required",
                "priority": "critical",
            }
        ],
    }
    result = parse_missing_items(payload, model_id="claude-sonnet-5", tokens_used=500)

    assert result.trade is Trade.ELECTRICAL
    assert result.completeness_score == 72
    assert len(result.missing) == 1
    assert result.missing[0].priority == "critical"


def test_parse_missing_unknown_trade_falls_back_to_general() -> None:
    payload = {"trade": "underwater basket weaving", "completeness_score": 50, "summary": "", "missing": []}
    result = parse_missing_items(payload, model_id="m", tokens_used=1)
    assert result.trade is Trade.GENERAL


def test_parse_missing_clamps_completeness_score() -> None:
    payload = {"trade": "hvac", "completeness_score": 250, "summary": "", "missing": []}
    assert parse_missing_items(payload, model_id="m", tokens_used=1).completeness_score == 100


def test_parse_missing_defaults_bad_quantity_to_one() -> None:
    payload = {
        "trade": "hvac",
        "completeness_score": 50,
        "summary": "",
        "missing": [
            {
                "description": "x",
                "category": "material",
                "item_name": "x",
                "estimated_quantity": 0,
                "unit": "each",
                "reasoning": "",
                "priority": "optional",
            }
        ],
    }
    result = parse_missing_items(payload, model_id="m", tokens_used=1)
    assert str(result.missing[0].estimated_quantity) == "1"


def test_parse_missing_rejects_unusable_item() -> None:
    payload = {
        "trade": "hvac",
        "completeness_score": 50,
        "summary": "",
        "missing": [{"category": "material"}],  # no description/item_name/priority
    }
    with pytest.raises(CopilotAnalysisError):
        parse_missing_items(payload, model_id="m", tokens_used=1)


# ── parse_rewrite ─────────────────────────────────────────────────────────────


def test_parse_rewrite_returns_texts_when_count_matches() -> None:
    payload = {"rewritten": ["one", "two"]}
    assert parse_rewrite(payload, expected_count=2) == ["one", "two"]


def test_parse_rewrite_count_mismatch_raises() -> None:
    with pytest.raises(CopilotAnalysisError):
        parse_rewrite({"rewritten": ["only one"]}, expected_count=2)


def test_parse_rewrite_non_list_raises() -> None:
    with pytest.raises(CopilotAnalysisError):
        parse_rewrite({"rewritten": "not a list"}, expected_count=1)


def test_parse_rewrite_ignores_extra_uuid_noise() -> None:
    # sanity: parser coerces non-str entries to str rather than crashing.
    assert parse_rewrite({"rewritten": [uuid.uuid4()]}, expected_count=1)
