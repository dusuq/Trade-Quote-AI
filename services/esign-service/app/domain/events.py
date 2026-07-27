"""E-signature domain events — Python mirror of the canonical registry in
`packages/types` (see docs/03-DOMAIN-EVENTS.md).

`esign.document.signed` and its `DocumentSignedPayload` are already declared
there; conventions §4 forbids inventing a local shape, so the payload keys
below match that interface field-for-field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

EsignEventName = Literal["esign.document.signed"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class DomainEvent:
    """Matches the TS `DomainEventEnvelope` shape 1:1."""

    event_name: EsignEventName
    tenant_id: UUID
    payload: dict[str, Any]
    actor_id: UUID | None = None
    event_version: int = 1
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: str = field(default_factory=_now)
    correlation_id: UUID | None = None
    causation_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": str(self.event_id),
            "eventName": self.event_name,
            "eventVersion": self.event_version,
            "tenantId": str(self.tenant_id),
            "actorId": str(self.actor_id) if self.actor_id else None,
            "occurredAt": self.occurred_at,
            "correlationId": str(self.correlation_id) if self.correlation_id else None,
            "causationId": str(self.causation_id) if self.causation_id else None,
            "payload": self.payload,
        }


def document_signed(
    tenant_id: UUID,
    *,
    proposal_id: UUID,
    signer_id: UUID,
    signature_hash: str,
    ip_address: str,
    signed_at: datetime,
) -> DomainEvent:
    """Keys mirror `DocumentSignedPayload` in packages/types/src/events.ts."""
    return DomainEvent(
        event_name="esign.document.signed",
        tenant_id=tenant_id,
        payload={
            "proposalId": str(proposal_id),
            "signerId": str(signer_id),
            "signatureHash": signature_hash,
            "ipAddress": ip_address,
            "signedAt": signed_at.astimezone(UTC).isoformat(),
        },
    )
