"""RewriteUseCase against in-memory fakes."""

from __future__ import annotations

import uuid

import pytest

from app.application.copilot_rewrite import RewriteUseCase
from app.domain.errors import DailySpendCapExceededError
from app.domain.models import AiFeature
from tests.fakes import FakeTextRewriter, InMemoryUsageRepository

TENANT = uuid.uuid4()
USER = uuid.uuid4()


def test_happy_path_rewrites_all_texts_in_order() -> None:
    rewriter = FakeTextRewriter()
    repo = InMemoryUsageRepository()
    use_case = RewriteUseCase(rewriter, repo)

    result, events = use_case.execute(
        tenant_id=TENANT,
        user_id=USER,
        texts=["install 200a panel", "12x 6in LED"],
        tone="professional",
    )

    assert len(result.rewritten) == 2
    assert result.rewritten[0].endswith("install 200a panel")
    assert len(repo.recorded) == 1
    assert repo.recorded[0].feature is AiFeature.COPILOT
    assert events[0].payload["feature"] == "copilot"


def test_invalid_tone_falls_back_to_professional() -> None:
    rewriter = FakeTextRewriter()
    use_case = RewriteUseCase(rewriter, InMemoryUsageRepository())

    use_case.execute(
        tenant_id=TENANT, user_id=USER, texts=["x"], tone="pirate"
    )

    # normalize_tone rejected "pirate" before it reached the rewriter/prompt.
    assert rewriter.calls[0][1] == "professional"


def test_context_hint_is_forwarded() -> None:
    rewriter = FakeTextRewriter()
    use_case = RewriteUseCase(rewriter, InMemoryUsageRepository())

    use_case.execute(
        tenant_id=TENANT,
        user_id=USER,
        texts=["x"],
        context_hint="electrical panel upgrade",
    )

    assert rewriter.calls[0][2] == "electrical panel upgrade"


def test_spend_cap_blocks_before_rewrite() -> None:
    rewriter = FakeTextRewriter()
    use_case = RewriteUseCase(
        rewriter, InMemoryUsageRepository(spend_today=50), daily_cap_minor=10
    )
    with pytest.raises(DailySpendCapExceededError):
        use_case.execute(tenant_id=TENANT, user_id=USER, texts=["x"])
    assert rewriter.calls == []
