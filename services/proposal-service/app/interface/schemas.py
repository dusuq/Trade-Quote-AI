"""Pydantic request/response DTOs for the HTTP interface."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class MoneyDto(BaseModel):
    amount_minor: int
    currency: str = "USD"


class CompanyBrandingDto(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    logo_path: str | None = None
    primary_color: str = "#111827"
    phone: str | None = None
    email: str | None = None
    website: str | None = None


class CustomerInfoDto(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    property_address: str | None = None


class LineItemDto(BaseModel):
    description: str
    quantity: float
    unit: str
    unit_price: MoneyDto
    line_total: MoneyDto


class RenderProposalRequest(BaseModel):
    quote_id: UUID
    branding: CompanyBrandingDto
    customer: CustomerInfoDto
    line_items: list[LineItemDto]
    subtotal: MoneyDto
    tax: MoneyDto
    total: MoneyDto
    scope_of_work: str = Field(min_length=1)
    warranty_text: str | None = None
    terms_text: str | None = None
    valid_until: str | None = None
    qr_payload_url: str | None = None


class RenderProposalResponse(BaseModel):
    proposal_id: UUID
    quote_id: UUID
    storage_key: str
    bytes: int
