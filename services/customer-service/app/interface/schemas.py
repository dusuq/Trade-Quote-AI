"""Pydantic request/response DTOs for the HTTP interface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateCustomerRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None


class CustomerResponse(BaseModel):
    id: UUID
    display_name: str
    company_name: str | None
    email: str | None
    phone: str | None
    created_at: datetime | None
    updated_at: datetime | None


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    page: int
    page_size: int
    total: int


class AddPropertyRequest(BaseModel):
    address_line1: str = Field(min_length=1)
    address_line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str = "US"
    lat: float | None = None
    lng: float | None = None


class PropertyResponse(BaseModel):
    id: UUID
    customer_id: UUID
    address_line1: str
    address_line2: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    country: str
    lat: float | None
    lng: float | None


class AddContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    is_primary: bool = False


class ContactResponse(BaseModel):
    id: UUID
    customer_id: UUID
    name: str
    email: str | None
    phone: str | None
    is_primary: bool


class AddNoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class NoteResponse(BaseModel):
    id: UUID
    customer_id: UUID
    body: str
    author_id: UUID | None
    created_at: datetime | None


class TagCustomerRequest(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    color: str | None = None


class TagResponse(BaseModel):
    id: UUID
    label: str
    color: str | None


class TimelineEntryResponse(BaseModel):
    kind: str
    occurred_at: datetime
    summary: str
    ref_id: UUID
