"""Domain entities for the Proposal Builder (M8) — persistence, templates,
and lifecycle on top of T107's stateless PDF engine. Framework-free: no
SQLAlchemy, no Pydantic (conventions §3 — customer-service is the gold
standard this follows).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class ProposalStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"


@dataclass(slots=True)
class ProposalTemplate:
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


@dataclass(slots=True)
class Proposal:
    id: UUID
    tenant_id: UUID
    quote_id: UUID
    template_id: UUID
    number: str
    status: ProposalStatus
    current_version: int
    storage_key: str | None
    sent_at: datetime | None
    viewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ProposalVersionRecord:
    id: UUID
    tenant_id: UUID
    proposal_id: UUID
    version: int
    snapshot: dict
    created_at: datetime


class TenantResolver(Protocol):
    def resolve(self, proposal_id: UUID) -> UUID | None:
        """Return the tenant_id owning `proposal_id`, or None if it doesn't
        exist. Used only by the public /view route, which has no tenant
        context to open a normal tenant-scoped session with."""
        ...
