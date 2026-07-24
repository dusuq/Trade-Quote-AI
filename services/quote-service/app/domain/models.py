"""SQLAlchemy ORM models for the quote-service."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class QuoteCreatedVia(str, enum.Enum):
    MANUAL = "manual"
    VOICE = "voice"
    VISION = "vision"
    OCR = "ocr"


class ItemKind(str, enum.Enum):
    MATERIAL = "material"
    LABOR = "labor"
    EQUIPMENT = "equipment"
    CONSUMABLE = "consumable"
    RENTAL = "rental"
    PACKAGE = "package"


class QuoteModel(Base):
    __tablename__ = "quote"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="quote_tenant_id_number_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    number: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, name="quote_status", create_type=False),
        nullable=False,
        default=QuoteStatus.DRAFT,
    )
    created_via: Mapped[QuoteCreatedVia] = mapped_column(
        Enum(QuoteCreatedVia, name="quote_created_via", create_type=False),
        nullable=False,
        default=QuoteCreatedVia.MANUAL,
    )
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    tax_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    line_items: Mapped[list[QuoteLineItemModel]] = relationship(
        "QuoteLineItemModel",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteLineItemModel.sort_order",
    )
    versions: Mapped[list[QuoteVersionModel]] = relationship(
        "QuoteVersionModel",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteVersionModel.version",
    )


class QuoteLineItemModel(Base):
    __tablename__ = "quote_line_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pricebook_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[ItemKind] = mapped_column(
        Enum(ItemKind, name="item_kind", create_type=False),
        nullable=False,
        default=ItemKind.MATERIAL,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=1.0)
    unit: Mapped[str] = mapped_column(String, nullable=False, default="each")
    unit_cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    markup_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )

    quote: Mapped[QuoteModel] = relationship("QuoteModel", back_populates="line_items")


class QuoteVersionModel(Base):
    __tablename__ = "quote_version"
    __table_args__ = (
        UniqueConstraint("quote_id", "version", name="quote_version_quote_id_version_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )

    quote: Mapped[QuoteModel] = relationship("QuoteModel", back_populates="versions")
