"""Pydantic request/response DTOs for the HTTP interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    company_name: str = Field(min_length=1, max_length=200)
    logo_url: str | None = None
    primary_color: str = "#111827"
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    default_terms_text: str | None = None
    default_warranty_text: str | None = None
    is_default: bool = False


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    logo_url: str | None = None
    primary_color: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    default_terms_text: str | None = None
    default_warranty_text: str | None = None
    is_default: bool | None = None


class TemplateResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    company_name: str
    logo_url: str | None
    primary_color: str
    phone: str | None
    email: str | None
    website: str | None
    default_terms_text: str | None
    default_warranty_text: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalCreate(BaseModel):
    quote_id: UUID
    template_id: UUID
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

    @field_validator("scope_of_work")
    @classmethod
    def _scope_of_work_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scope_of_work must not be blank")
        return value


class ProposalVersionResponse(BaseModel):
    id: UUID
    version: int
    snapshot: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    quote_id: UUID
    template_id: UUID
    number: str
    status: str
    current_version: int
    storage_key: str | None
    sent_at: datetime | None
    viewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalSendRequest(BaseModel):
    channel: str = Field(default="email", description="email, sms, or link")
