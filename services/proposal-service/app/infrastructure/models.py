"""SQLAlchemy ORM models for the Proposal Builder (M8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.proposal import ProposalStatus
from app.infrastructure.db import Base


class ProposalTemplateModel(Base):
    __tablename__ = "proposal_template"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_color: Mapped[str] = mapped_column(String, nullable=False, default="#111827")
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    default_terms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_warranty_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class ProposalModel(Base):
    __tablename__ = "proposal"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="proposal_tenant_id_number_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(
            ProposalStatus,
            name="proposal_status",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ProposalStatus.DRAFT,
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    versions: Mapped[list[ProposalVersionModel]] = relationship(
        "ProposalVersionModel",
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="ProposalVersionModel.version",
    )


class ProposalVersionModel(Base):
    __tablename__ = "proposal_version"
    __table_args__ = (UniqueConstraint("proposal_id", "version", name="proposal_version_proposal_id_version_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposal.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )

    proposal: Mapped[ProposalModel] = relationship("ProposalModel", back_populates="versions")
