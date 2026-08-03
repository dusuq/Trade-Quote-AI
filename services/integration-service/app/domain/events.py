"""Integration domain events — Python mirror of the canonical registry in
`packages/types` (see docs/03-DOMAIN-EVENTS.md). Producers persist these via
the transactional outbox in the same DB transaction as the state change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

IntegrationEventName = Literal[
    "integration.connection.created",
    "integration.connection.activated",
    "integration.connection.revoked",
    "integration.sync.completed",
    "integration.webhook.fired",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class DomainEvent:
    """Matches the TS `DomainEventEnvelope` shape 1:1."""

    event_name: IntegrationEventName
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


def connection_created(
    tenant_id: UUID, connection_id: UUID, provider: str,
) -> DomainEvent:
    return DomainEvent(
        event_name="integration.connection.created",
        tenant_id=tenant_id,
        payload={"connectionId": str(connection_id), "provider": provider},
    )


def connection_activated(
    tenant_id: UUID, connection_id: UUID, provider: str, external_account_id: str | None,
) -> DomainEvent:
    return DomainEvent(
        event_name="integration.connection.activated",
        tenant_id=tenant_id,
        payload={
            "connectionId": str(connection_id),
            "provider": provider,
            "externalAccountId": external_account_id,
        },
    )


def connection_revoked(
    tenant_id: UUID, connection_id: UUID, provider: str,
) -> DomainEvent:
    return DomainEvent(
        event_name="integration.connection.revoked",
        tenant_id=tenant_id,
        payload={"connectionId": str(connection_id), "provider": provider},
    )


def sync_completed(
    tenant_id: UUID,
    connection_id: UUID,
    sync_log_id: UUID,
    entity_type: str,
    direction: str,
    status: str,
) -> DomainEvent:
    return DomainEvent(
        event_name="integration.sync.completed",
        tenant_id=tenant_id,
        payload={
            "connectionId": str(connection_id),
            "syncLogId": str(sync_log_id),
            "entityType": entity_type,
            "direction": direction,
            "status": status,
        },
    )


def webhook_fired(
    tenant_id: UUID,
    connection_id: UUID,
    webhook_id: UUID,
    event_type: str,
    target_url: str,
) -> DomainEvent:
    return DomainEvent(
        event_name="integration.webhook.fired",
        tenant_id=tenant_id,
        payload={
            "connectionId": str(connection_id),
            "webhookId": str(webhook_id),
            "eventType": event_type,
            "targetUrl": target_url,
        },
    )
