"""Customer domain events — Python mirror of the canonical registry in
`packages/types` (see docs/03-DOMAIN-EVENTS.md). Producers persist these via
the transactional outbox in the same DB transaction as the state change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

CustomerEventName = Literal["customer.customer.created", "customer.property.added"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class DomainEvent:
    """Matches the TS `DomainEventEnvelope` shape 1:1."""

    event_name: CustomerEventName
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


def customer_created(tenant_id: UUID, customer_id: UUID, display_name: str) -> DomainEvent:
    return DomainEvent(
        event_name="customer.customer.created",
        tenant_id=tenant_id,
        payload={
            "customerId": str(customer_id),
            "displayName": display_name,
            "primaryContactId": None,
        },
    )


def property_added(
    tenant_id: UUID, customer_id: UUID, property_id: UUID, address_line1: str
) -> DomainEvent:
    return DomainEvent(
        event_name="customer.property.added",
        tenant_id=tenant_id,
        payload={
            "customerId": str(customer_id),
            "propertyId": str(property_id),
            "addressLine1": address_line1,
        },
    )
