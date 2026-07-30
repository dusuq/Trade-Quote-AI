"""AnalyzePricingUseCase against in-memory fakes."""

from __future__ import annotations

import uuid

import pytest

from app.application.copilot_pricing import AnalyzePricingUseCase
from app.domain.errors import DailySpendCapExceededError, QuoteNotFoundError
from app.domain.models import AiFeature
from tests.fakes import (
    FakeCopilotAnalyzer,
    FakePricebookMatcher,
    FakeQuoteReader,
    InMemoryUsageRepository,
    make_line_item,
    make_match,
    make_snapshot,
)

TENANT = uuid.uuid4()
USER = uuid.uuid4()


def _use_case(**overrides):
    reader = overrides.get("reader", FakeQuoteReader())
    matcher = overrides.get("matcher", FakePricebookMatcher())
    analyzer = overrides.get("analyzer", FakeCopilotAnalyzer())
    repo = overrides.get("repo", InMemoryUsageRepository())
    use_case = AnalyzePricingUseCase(
        reader, matcher, analyzer, repo, daily_cap_minor=overrides.get("cap", 0)
    )
    return use_case, reader, matcher, analyzer, repo


def test_happy_path_reads_quote_matches_and_analyzes() -> None:
    use_case, reader, _matcher, analyzer, repo = _use_case()

    result, events = use_case.execute(
        tenant_id=TENANT, user_id=USER, quote_id=reader.snapshot.quote_id
    )

    assert reader.calls == [reader.snapshot.quote_id]
    assert analyzer.pricing_calls  # LLM analyzer was invoked
    assert len(result.suggestions) == len(reader.snapshot.line_items)
    assert result.margin.total_revenue_minor == reader.snapshot.subtotal_minor
    # Usage recorded and one ai.usage.recorded event emitted, feature = copilot.
    assert len(repo.recorded) == 1
    assert repo.recorded[0].feature is AiFeature.COPILOT
    assert [e.event_name for e in events] == ["ai.usage.recorded"]
    assert events[0].payload["feature"] == "copilot"


def test_pricebook_match_is_attached_to_the_right_line() -> None:
    line = make_line_item(description="200A main breaker panel")
    reader = FakeQuoteReader(make_snapshot(line_items=(line,)))
    matcher = FakePricebookMatcher({"200A main breaker panel": make_match(unit_cost_minor=77_000)})
    use_case, *_ = _use_case(reader=reader, matcher=matcher)

    result, _ = use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=line.id)

    assert result.suggestions[0].pricebook_unit_cost_minor == 77_000


def test_empty_quote_is_graceful_and_costs_nothing() -> None:
    reader = FakeQuoteReader(make_snapshot(line_items=()))
    use_case, _, _, analyzer, repo = _use_case(reader=reader)

    result, events = use_case.execute(
        tenant_id=TENANT, user_id=USER, quote_id=reader.snapshot.quote_id
    )

    assert result.suggestions == ()
    assert result.tokens_used == 0
    assert analyzer.pricing_calls == []  # no model call
    assert repo.recorded == []  # nothing billed
    assert events == []


def test_quote_not_found_propagates() -> None:
    reader = FakeQuoteReader(found=False)
    use_case, *_ = _use_case(reader=reader)

    with pytest.raises(QuoteNotFoundError):
        use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=uuid.uuid4())


def test_spend_cap_blocks_before_reading_quote() -> None:
    reader = FakeQuoteReader()
    repo = InMemoryUsageRepository(spend_today=500)
    use_case, *_ = _use_case(reader=reader, repo=repo, cap=100)

    with pytest.raises(DailySpendCapExceededError):
        use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=uuid.uuid4())

    assert reader.calls == []  # cap enforced before any work
