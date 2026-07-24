"""Pydantic schemas (DTOs) for the pricebook-service."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ItemKind


class PricebookRegionPriceCreate(BaseModel):
    region_code: str = Field(..., description="Region code e.g. 'US-CA', 'US-NY', 'AU-NSW'")
    unit_cost_minor: int = Field(..., ge=0, description="Unit cost in minor units (cents)")


class PricebookRegionPriceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    item_id: uuid.UUID
    region_code: str
    unit_cost_minor: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PricebookItemCreate(BaseModel):
    kind: ItemKind
    sku: str | None = Field(default=None, description="Unique SKU code per tenant")
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    unit: str = Field(default="each", description="Unit of measure e.g. each, hour, ft, m, box")
    unit_cost_minor: int = Field(default=0, ge=0, description="Default unit cost in minor units (cents)")
    default_markup_bps: int = Field(default=0, ge=0, description="Default markup in basis points (10000 = 100%)")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    is_active: bool = True


class PricebookItemUpdate(BaseModel):
    kind: ItemKind | None = None
    sku: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    unit: str | None = None
    unit_cost_minor: int | None = Field(default=None, ge=0)
    default_markup_bps: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_active: bool | None = None


class PricebookItemResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    kind: ItemKind
    sku: str | None
    name: str
    description: str | None
    unit: str
    unit_cost_minor: int
    default_markup_bps: int
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    region_prices: list[PricebookRegionPriceResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EffectivePriceResponse(BaseModel):
    item_id: uuid.UUID
    name: str
    sku: str | None
    unit: str
    currency: str
    region_code: str | None
    unit_cost_minor: int
    default_markup_bps: int
    calculated_price_minor: int  # unit_cost_minor * (1 + default_markup_bps / 10000)


class PricebookImportSummary(BaseModel):
    total_rows: int
    created: int
    updated: int
    errors: list[str] = Field(default_factory=list)
