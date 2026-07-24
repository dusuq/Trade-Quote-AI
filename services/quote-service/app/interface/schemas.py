"""Pydantic schemas (DTOs) for the quote-service interface layer."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ItemKind, QuoteCreatedVia, QuoteStatus


class LineItemCreate(BaseModel):
    pricebook_item_id: uuid.UUID | None = None
    kind: ItemKind = ItemKind.MATERIAL
    description: str = Field(..., min_length=1)
    quantity: float = Field(default=1.0, gt=0)
    unit: str = Field(default="each")
    unit_cost_minor: int = Field(default=0, ge=0)
    markup_bps: int = Field(default=0, ge=0)
    unit_price_minor: int | None = Field(
        default=None,
        ge=0,
        description="If omitted, unit_price_minor is computed from unit_cost_minor * (1 + markup_bps/10000)",
    )
    is_optional: bool = False
    sort_order: int = 0


class LineItemUpdate(BaseModel):
    pricebook_item_id: uuid.UUID | None = None
    kind: ItemKind | None = None
    description: str | None = Field(default=None, min_length=1)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    unit_cost_minor: int | None = Field(default=None, ge=0)
    markup_bps: int | None = Field(default=None, ge=0)
    unit_price_minor: int | None = Field(default=None, ge=0)
    is_optional: bool | None = None
    sort_order: int | None = None


class LineItemResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    quote_id: uuid.UUID
    pricebook_item_id: uuid.UUID | None
    kind: ItemKind
    description: str
    quantity: float
    unit: str
    unit_cost_minor: int
    markup_bps: int
    unit_price_minor: int
    line_total_minor: int
    is_optional: bool
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuoteCreate(BaseModel):
    customer_id: uuid.UUID
    property_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    created_via: QuoteCreatedVia = QuoteCreatedVia.MANUAL
    currency: str = Field(default="USD", min_length=3, max_length=3)
    tax_rate_bps: int = Field(default=0, ge=0, description="Tax rate in basis points (e.g. 875 = 8.75%)")
    valid_until: date | None = None
    owner_id: uuid.UUID | None = None
    initial_line_items: list[LineItemCreate] = Field(default_factory=list)


class QuoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    property_id: uuid.UUID | None = None
    tax_rate_bps: int | None = Field(default=None, ge=0)
    valid_until: date | None = None
    owner_id: uuid.UUID | None = None


class QuoteResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    property_id: uuid.UUID | None
    number: str
    title: str | None
    status: QuoteStatus
    created_via: QuoteCreatedVia
    currency: str
    tax_rate_bps: int
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    current_version: int
    valid_until: date | None
    owner_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    line_items: list[LineItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class QuoteVersionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    quote_id: uuid.UUID
    version: int
    snapshot: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuoteSendRequest(BaseModel):
    channel: str = Field(default="email", description="Channel sent via e.g. email, sms, link, whatsapp")


class QuoteRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
