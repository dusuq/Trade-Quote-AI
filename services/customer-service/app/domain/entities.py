"""Domain entities (framework-free, pure Python) — mirror of infra/db/migrations/0003_customer.sql."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Customer:
    id: UUID
    tenant_id: UUID
    display_name: str
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class Contact:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    name: str
    email: str | None = None
    phone: str | None = None
    is_primary: bool = False
    created_at: datetime | None = None


@dataclass(slots=True)
class Property:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    address_line1: str
    address_line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str = "US"
    lat: float | None = None
    lng: float | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class Tag:
    id: UUID
    tenant_id: UUID
    label: str
    color: str | None = None


@dataclass(slots=True)
class CustomerNote:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    body: str
    author_id: UUID | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class TimelineEntry:
    """A single chronological event on a customer's timeline. `kind` is
    extensible — today only "note", future services (quote, proposal,
    payment) append their own kinds once they publish domain events this
    service can project into the timeline.
    """

    kind: str
    occurred_at: datetime
    summary: str
    ref_id: UUID
    extra: dict = field(default_factory=dict)
