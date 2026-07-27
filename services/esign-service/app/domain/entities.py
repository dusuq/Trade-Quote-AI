"""Domain entities for E-Signature (M10 / T204).

Framework-free — no SQLAlchemy, no Pydantic (conventions §3; customer-service
is the gold standard this follows).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


class SignatureRequestStatus(str, enum.Enum):
    PENDING = "pending"
    SIGNED = "signed"
    DECLINED = "declined"
    VOIDED = "voided"
    EXPIRED = "expired"


class SignatureMethod(str, enum.Enum):
    TYPED = "typed"
    DRAWN = "drawn"


class AuditEventType(str, enum.Enum):
    """Every state change that gets a link in the hash chain."""

    REQUEST_CREATED = "request.created"
    DOCUMENT_OPENED = "document.opened"
    SIGNATURE_APPLIED = "signature.applied"
    REQUEST_DECLINED = "request.declined"
    REQUEST_VOIDED = "request.voided"


@dataclass(slots=True)
class SignatureRequest:
    """One ask for one signer to sign one proposal.

    `token` is the capability for the public signing link — high-entropy and
    independently revocable, so voiding a link never touches the proposal
    (design spec D2).

    `signer_id` is a stable synthetic identity for an external signer who has
    no TradeQuote account; it is what the canonical `esign.document.signed`
    event carries as `signerId`.
    """

    id: UUID
    tenant_id: UUID
    proposal_id: UUID
    signer_id: UUID
    signer_name: str
    signer_email: str
    token: str
    document_sha256: str
    status: SignatureRequestStatus
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    signed_at: datetime | None = None
    declined_at: datetime | None = None
    voided_at: datetime | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def is_open(self, now: datetime) -> bool:
        """Can this still be acted on by the signer?

        Expiry is evaluated against the clock rather than trusting the stored
        status, so a request that lapsed while nobody was looking behaves as
        expired without needing a sweeper job to have run first.
        """
        return self.status == SignatureRequestStatus.PENDING and not self.is_expired(now)


@dataclass(slots=True)
class Signature:
    """The captured signature and its evidence bundle."""

    id: UUID
    tenant_id: UUID
    request_id: UUID
    signer_id: UUID
    signer_name: str
    signer_email: str
    method: SignatureMethod
    typed_name: str | None
    image_data: str | None
    signature_hash: str
    document_sha256: str
    ip_address: str
    user_agent: str | None
    consented_to_electronic_business: bool
    intent_affirmed: bool
    signed_at: datetime


@dataclass(slots=True)
class AuditEvent:
    """One immutable link in a signature request's hash chain.

    Attribute names match what `hash_chain.verify_chain` reads.
    """

    id: UUID
    tenant_id: UUID
    request_id: UUID
    sequence: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    prev_hash: str
    entry_hash: str
