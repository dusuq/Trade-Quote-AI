"""Auth domain events — Python mirror of the canonical registry in
`packages/types` (see docs/03-DOMAIN-EVENTS.md). Producers persist these via
the transactional outbox in the same DB transaction as the state change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

AuthEventName = Literal["auth.tenant.created", "auth.user.invited"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DomainEvent:
    """Matches the TS `DomainEventEnvelope` shape 1:1."""

    event_name: AuthEventName
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


def tenant_created(tenant_id: UUID, name: str, plan: str) -> DomainEvent:
    return DomainEvent(
        event_name="auth.tenant.created",
        tenant_id=tenant_id,
        payload={"tenantId": str(tenant_id), "name": name, "plan": plan},
    )


def user_invited(tenant_id: UUID, user_id: UUID, email: str, role: str) -> DomainEvent:
    return DomainEvent(
        event_name="auth.user.invited",
        tenant_id=tenant_id,
        actor_id=None,
        payload={"userId": str(user_id), "email": email, "role": role},
    )
