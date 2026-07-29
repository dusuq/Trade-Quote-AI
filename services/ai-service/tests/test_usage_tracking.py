"""AI usage persistence: the billing/cost-control record."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.domain.models import AiFeature, AiUsage
from app.infrastructure.models import AiUsageLogORM
from app.infrastructure.usage_repository import (
    BufferedAiUsageRepository,
    SqlAlchemyAiUsageRepository,
)


def make_usage(cost_minor: int = 7, tokens: int = 1_200) -> AiUsage:
    return AiUsage(
        feature=AiFeature.VOICE,
        model_id="claude-opus-5",
        input_kind="voice",
        tokens_used=tokens,
        cost_minor=cost_minor,
        metadata={"input_tokens": 1_000, "output_tokens": 200},
    )


def test_records_and_reads_back(db_session, tenant_id) -> None:
    repo = SqlAlchemyAiUsageRepository(db_session)

    repo.record(tenant_id, make_usage())
    db_session.expire_all()

    rows = repo.list_for_tenant(tenant_id)
    assert len(rows) == 1
    assert rows[0].model_id == "claude-opus-5"
    assert rows[0].cost_minor == 7
    assert rows[0].metadata["output_tokens"] == 200


def test_timestamps_come_back_timezone_aware(db_session, tenant_id) -> None:
    """SQLite drops tzinfo; a naive value would compare wrongly against
    `datetime.now(UTC)` in the daily-spend window."""
    repo = SqlAlchemyAiUsageRepository(db_session)
    repo.record(tenant_id, make_usage())
    db_session.expire_all()

    assert repo.list_for_tenant(tenant_id)[0].created_at.tzinfo is not None


def test_listing_is_newest_first(db_session, tenant_id) -> None:
    repo = SqlAlchemyAiUsageRepository(db_session)
    for tokens in (100, 200, 300):
        repo.record(tenant_id, make_usage(tokens=tokens))
    db_session.expire_all()

    rows = repo.list_for_tenant(tenant_id)

    assert len(rows) == 3
    assert rows[0].created_at >= rows[-1].created_at


def test_pagination(db_session, tenant_id) -> None:
    repo = SqlAlchemyAiUsageRepository(db_session)
    for _ in range(5):
        repo.record(tenant_id, make_usage())
    db_session.expire_all()

    assert len(repo.list_for_tenant(tenant_id, skip=0, limit=2)) == 2
    assert len(repo.list_for_tenant(tenant_id, skip=4, limit=2)) == 1


def test_spend_today_sums_only_this_tenant(db_session, tenant_id, other_tenant_id) -> None:
    repo = SqlAlchemyAiUsageRepository(db_session)
    repo.record(tenant_id, make_usage(cost_minor=10))
    repo.record(tenant_id, make_usage(cost_minor=5))
    repo.record(other_tenant_id, make_usage(cost_minor=999))
    db_session.expire_all()

    assert repo.spend_today_minor(tenant_id) == 15
    assert repo.spend_today_minor(other_tenant_id) == 999


def test_spend_today_excludes_yesterday(db_session, tenant_id) -> None:
    """The cap is a *daily* budget — yesterday's spend must not count."""
    db_session.add(
        AiUsageLogORM(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            feature="voice",
            model_id="claude-opus-5",
            input_kind="voice",
            tokens_used=100,
            cost_minor=500,
            usage_metadata={},
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.flush()

    assert SqlAlchemyAiUsageRepository(db_session).spend_today_minor(tenant_id) == 0


def test_spend_today_is_zero_with_no_rows(db_session, tenant_id) -> None:
    assert SqlAlchemyAiUsageRepository(db_session).spend_today_minor(tenant_id) == 0


def test_unknown_feature_does_not_break_the_listing(db_session, tenant_id) -> None:
    """A row written by a newer version shouldn't 500 the usage endpoint."""
    db_session.add(
        AiUsageLogORM(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            feature="some_future_feature",
            model_id="claude-opus-5",
            input_kind="text",
            tokens_used=1,
            cost_minor=1,
            usage_metadata={},
            created_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    assert len(SqlAlchemyAiUsageRepository(db_session).list_for_tenant(tenant_id)) == 1


def test_buffered_repository_defers_writes(tenant_id) -> None:
    """ADR-0003 rule 3: usage is buffered so no transaction stays open across
    the pipeline's network calls."""
    repo = BufferedAiUsageRepository(spend_today_minor=42)

    repo.record(tenant_id, make_usage())
    repo.record(tenant_id, make_usage())

    assert len(repo.pending) == 2
    assert repo.spend_today_minor(tenant_id) == 42
