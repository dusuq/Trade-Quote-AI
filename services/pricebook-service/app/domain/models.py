"""SQLAlchemy ORM models for the pricebook-service."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ItemKind(str, enum.Enum):
    MATERIAL = "material"
    LABOR = "labor"
    EQUIPMENT = "equipment"
    CONSUMABLE = "consumable"
    RENTAL = "rental"
    PACKAGE = "package"


class PricebookItemModel(Base):
    __tablename__ = "pricebook_item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="pricebook_item_tenant_id_sku_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[ItemKind] = mapped_column(
        Enum(
            ItemKind,
            name="item_kind",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    sku: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String, nullable=False, default="each")
    unit_cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    default_markup_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    region_prices: Mapped[list[PricebookRegionPriceModel]] = relationship(
        "PricebookRegionPriceModel",
        back_populates="item",
        cascade="all, delete-orphan",
    )


class PricebookRegionPriceModel(Base):
    __tablename__ = "pricebook_region_price"
    __table_args__ = (
        UniqueConstraint("item_id", "region_code", name="pricebook_region_price_item_id_region_code_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pricebook_item.id", ondelete="CASCADE"), nullable=False
    )
    region_code: Mapped[str] = mapped_column(String, nullable=False)
    unit_cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )

    item: Mapped[PricebookItemModel] = relationship(
        "PricebookItemModel", back_populates="region_prices"
    )
