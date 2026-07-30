"""Copilot request/response DTO validation and mappers."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.interface.schemas import (
    AnalyzePricingRequest,
    MissingItemsRequest,
    RewriteRequest,
    to_missing_items_response,
    to_pricing_analysis_response,
    to_rewrite_response,
)
from tests.fakes import FakeCopilotAnalyzer, FakeTextRewriter, make_snapshot


def test_analyze_pricing_request_requires_uuid() -> None:
    ok = AnalyzePricingRequest(quote_id=uuid.uuid4())
    assert isinstance(ok.quote_id, uuid.UUID)
    with pytest.raises(ValidationError):
        AnalyzePricingRequest(quote_id="not-a-uuid")


def test_rewrite_request_rejects_empty_and_overlong_lists() -> None:
    with pytest.raises(ValidationError):
        RewriteRequest(texts=[])
    with pytest.raises(ValidationError):
        RewriteRequest(texts=["x"] * 51)
    ok = RewriteRequest(texts=["install panel"])
    assert ok.tone == "professional"  # default


def test_missing_items_request_caps_job_description() -> None:
    with pytest.raises(ValidationError):
        MissingItemsRequest(quote_id=uuid.uuid4(), job_description="x" * 10_001)


def test_pricing_response_mapper_preserves_money_as_int() -> None:
    quote = make_snapshot()
    result, _ = FakeCopilotAnalyzer().analyze_pricing(quote, {})

    dto = to_pricing_analysis_response(quote.quote_id, result)

    assert dto.quote_id == quote.quote_id
    assert len(dto.suggestions) == len(quote.line_items)
    assert isinstance(dto.margin.total_cost_minor, int)
    assert isinstance(dto.margin.gross_margin_bps, int)
    assert all(isinstance(s.current_unit_cost_minor, int) for s in dto.suggestions)


def test_missing_response_mapper_keeps_quantity_decimal() -> None:
    quote = make_snapshot()
    result, _ = FakeCopilotAnalyzer().find_missing_items(quote, None)

    dto = to_missing_items_response(quote.quote_id, result)

    assert dto.trade == "electrical"
    assert isinstance(dto.missing[0].estimated_quantity, Decimal)


def test_rewrite_response_mapper() -> None:
    rewritten, _ = FakeTextRewriter().rewrite(["a", "b"], "professional")
    from app.domain.models import RewriteResult

    dto = to_rewrite_response(
        RewriteResult(rewritten=tuple(rewritten), model_id="claude-sonnet-5", tokens_used=10)
    )
    assert dto.rewritten == rewritten
    assert dto.model_id == "claude-sonnet-5"
