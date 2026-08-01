"""SalesCoachUseCase against in-memory fakes."""

from __future__ import annotations

import uuid

import pytest

from app.application.sales_coach import SalesCoachUseCase
from app.domain.errors import DailySpendCapExceededError, QuoteNotFoundError
from app.domain.models import AiFeature
from tests.fakes import (
    FakeQuoteReader,
    FakeSalesCoachAnalyzer,
    InMemoryUsageRepository,
    make_snapshot,
)

TENANT = uuid.uuid4()
USER = uuid.uuid4()


def test_happy_path_returns_suggestions_and_records_usage() -> None:
    reader = FakeQuoteReader()
    analyzer = FakeSalesCoachAnalyzer()
    repo = InMemoryUsageRepository()
    use_case = SalesCoachUseCase(reader, analyzer, repo)

    result, events = use_case.execute(
        tenant_id=TENANT, user_id=USER, quote_id=reader.snapshot.quote_id
    )

    assert result.suggestions
    assert analyzer.calls == [reader.snapshot]
    assert len(repo.recorded) == 1
    assert repo.recorded[0].feature is AiFeature.SALES_COACH
    assert events[0].payload["feature"] == "sales_coach"


def test_the_quote_is_never_mutated() -> None:
    """Read-only really means read-only — the use case has no reference to
    a QuoteCreator or any write path at all."""
    use_case = SalesCoachUseCase(
        FakeQuoteReader(), FakeSalesCoachAnalyzer(), InMemoryUsageRepository()
    )
    assert not hasattr(use_case, "_quote_creator")


def test_empty_quote_still_gets_analyzed() -> None:
    reader = FakeQuoteReader(make_snapshot(line_items=()))
    analyzer = FakeSalesCoachAnalyzer()
    use_case = SalesCoachUseCase(reader, analyzer, InMemoryUsageRepository())

    use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=reader.snapshot.quote_id)

    assert analyzer.calls  # the model was consulted even with no line items


def test_empty_suggestions_list_is_a_valid_result() -> None:
    """No relevant upsell is a legitimate answer, not an error — unlike
    missing-items (a gap in the job) or vision/OCR (nothing to extract)."""
    reader = FakeQuoteReader()
    analyzer = FakeSalesCoachAnalyzer(suggestions=())
    use_case = SalesCoachUseCase(reader, analyzer, InMemoryUsageRepository())

    result, _events = use_case.execute(
        tenant_id=TENANT, user_id=USER, quote_id=reader.snapshot.quote_id
    )

    assert result.suggestions == ()


def test_quote_not_found_propagates() -> None:
    use_case = SalesCoachUseCase(
        FakeQuoteReader(found=False), FakeSalesCoachAnalyzer(), InMemoryUsageRepository()
    )
    with pytest.raises(QuoteNotFoundError):
        use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=uuid.uuid4())


def test_spend_cap_blocks_before_the_quote_is_read() -> None:
    reader = FakeQuoteReader()
    use_case = SalesCoachUseCase(
        reader,
        FakeSalesCoachAnalyzer(),
        InMemoryUsageRepository(spend_today=999),
        daily_cap_minor=10,
    )
    with pytest.raises(DailySpendCapExceededError):
        use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=uuid.uuid4())
    assert reader.calls == []
