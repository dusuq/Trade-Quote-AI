"""Concrete `AiUsageRepository` over SQLAlchemy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import AiFeature, AiUsage, AiUsageRecord
from app.infrastructure.models import AiUsageLogORM


def _ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime read back from the database to aware UTC.

    SQLite (the test harness) stores no timezone, so values come back naive
    and would compare incorrectly against `datetime.now(UTC)`.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _start_of_utc_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class BufferedAiUsageRepository:
    """Collects usage in memory; the caller persists it afterwards.

    This exists to satisfy ADR-0003 rule 3 — *no network I/O inside an open
    database transaction*. The quote pipeline makes blocking calls to an LLM
    and two services, so it cannot hold a pooled connection while it runs.

    So the route reads spend-to-date in one short transaction, runs the
    pipeline with no transaction open, then writes the buffered usage in
    another short transaction. Same data, no connection pinned across the
    network work.
    """

    def __init__(self, spend_today_minor: int = 0) -> None:
        self._spend_today_minor = spend_today_minor
        self.pending: list[AiUsage] = []

    def record(self, tenant_id: UUID, usage: AiUsage) -> None:
        self.pending.append(usage)

    def spend_today_minor(self, tenant_id: UUID) -> int:
        return self._spend_today_minor

    def list_for_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AiUsageRecord]:
        raise NotImplementedError("buffered repository is write-only")


class SqlAlchemyAiUsageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, tenant_id: UUID, usage: AiUsage) -> None:
        self.session.add(
            AiUsageLogORM(
                id=uuid4(),
                tenant_id=tenant_id,
                feature=usage.feature.value,
                model_id=usage.model_id,
                input_kind=usage.input_kind,
                tokens_used=usage.tokens_used,
                cost_minor=usage.cost_minor,
                usage_metadata=dict(usage.metadata),
                created_at=datetime.now(UTC),
            )
        )
        self.session.flush()

    def list_for_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AiUsageRecord]:
        stmt = (
            select(AiUsageLogORM)
            .where(AiUsageLogORM.tenant_id == tenant_id)
            .order_by(AiUsageLogORM.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return [self._to_domain(row) for row in self.session.scalars(stmt).all()]

    def spend_today_minor(self, tenant_id: UUID) -> int:
        """Total cost booked for this tenant since 00:00 UTC.

        The window is UTC rather than the tenant's local day: a cost control
        only has to be consistent and predictable, and a tenant-local window
        would need a timezone this table doesn't carry.
        """
        now = datetime.now(UTC)
        total = self.session.scalar(
            select(func.coalesce(func.sum(AiUsageLogORM.cost_minor), 0)).where(
                AiUsageLogORM.tenant_id == tenant_id,
                AiUsageLogORM.created_at >= _start_of_utc_day(now),
                AiUsageLogORM.created_at < _start_of_utc_day(now) + timedelta(days=1),
            )
        )
        return int(total or 0)

    @staticmethod
    def _to_domain(row: AiUsageLogORM) -> AiUsageRecord:
        try:
            feature = AiFeature(row.feature)
        except ValueError:
            # A row written by a newer version of the service shouldn't make
            # the usage endpoint fail for everything else.
            feature = AiFeature.VOICE
        return AiUsageRecord(
            feature=feature,
            model_id=row.model_id,
            input_kind=row.input_kind,
            tokens_used=row.tokens_used,
            cost_minor=row.cost_minor,
            metadata=dict(row.usage_metadata or {}),
            id=row.id,
            created_at=_ensure_utc(row.created_at),
        )
