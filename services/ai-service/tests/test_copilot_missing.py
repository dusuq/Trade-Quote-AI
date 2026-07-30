"""FindMissingItemsUseCase against in-memory fakes."""

from __future__ import annotations

import uuid

import pytest

from app.application.copilot_missing import FindMissingItemsUseCase
from app.domain.errors import DailySpendCapExceededError, QuoteNotFoundError
from app.domain.models import AiFeature
from tests.fakes import (
    FakeCopilotAnalyzer,
    FakeQuoteReader,
    InMemoryUsageRepository,
    make_snapshot,
)

TENANT = uuid.uuid4()
USER = uuid.uuid4()


def test_happy_path_returns_missing_items_and_records_usage() -> None:
    reader = FakeQuoteReader()
    analyzer = FakeCopilotAnalyzer()
    repo = InMemoryUsageRepository()
    use_case = FindMissingItemsUseCase(reader, analyzer, repo)

    result, events = use_case.execute(
        tenant_id=TENANT,
        user_id=USER,
        quote_id=reader.snapshot.quote_id,
        job_description="200A panel upgrade",
    )

    assert result.missing  # at least one suggestion
    assert result.completeness_score == 80
    assert analyzer.missing_calls[0][1] == "200A panel upgrade"  # description forwarded
    assert len(repo.recorded) == 1
    assert repo.recorded[0].feature is AiFeature.COPILOT
    assert events[0].payload["feature"] == "copilot"


def test_job_description_is_optional() -> None:
    reader = FakeQuoteReader()
    analyzer = FakeCopilotAnalyzer()
    use_case = FindMissingItemsUseCase(reader, analyzer, InMemoryUsageRepository())

    use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=reader.snapshot.quote_id)

    assert analyzer.missing_calls[0][1] is None


def test_empty_quote_still_analyzes() -> None:
    # An empty quote is a valid input here — everything is "missing".
    reader = FakeQuoteReader(make_snapshot(line_items=()))
    analyzer = FakeCopilotAnalyzer()
    use_case = FindMissingItemsUseCase(reader, analyzer, InMemoryUsageRepository())

    result, _ = use_case.execute(
        tenant_id=TENANT, user_id=USER, quote_id=reader.snapshot.quote_id
    )

    assert analyzer.missing_calls  # the model was consulted
    assert result.trade.value == "electrical"


def test_quote_not_found_propagates() -> None:
    use_case = FindMissingItemsUseCase(
        FakeQuoteReader(found=False), FakeCopilotAnalyzer(), InMemoryUsageRepository()
    )
    with pytest.raises(QuoteNotFoundError):
        use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=uuid.uuid4())


def test_spend_cap_blocks_before_work() -> None:
    reader = FakeQuoteReader()
    use_case = FindMissingItemsUseCase(
        reader, FakeCopilotAnalyzer(), InMemoryUsageRepository(spend_today=999), daily_cap_minor=10
    )
    with pytest.raises(DailySpendCapExceededError):
        use_case.execute(tenant_id=TENANT, user_id=USER, quote_id=uuid.uuid4())
    assert reader.calls == []
