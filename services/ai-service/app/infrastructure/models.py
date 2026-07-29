"""SQLAlchemy ORM models for AI usage tracking (M15 / T201)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AiUsageLogORM(Base):
    """One metered AI call.

    `feature`, `model_id`, and `input_kind` are plain strings rather than
    Postgres enums: this table is append-only telemetry that must keep
    accepting rows when a new model id or feature ships, and a schema
    migration is a poor gate on writing a usage record. (It also sidesteps
    the `values_callable` enum trap from T206b entirely.)
    """

    __tablename__ = "ai_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Money in minor units; BigInteger because a busy tenant's lifetime spend
    # in cents should never be the thing that overflows.
    cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    usage_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
