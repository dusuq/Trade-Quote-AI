"""Notification domain events — Python mirror of the canonical registry in
`packages/types` (see docs/03-DOMAIN-EVENTS.md).

`notification.message.sent` and its `NotificationSentPayload` are already
declared there; conventions §4 forbids inventing a local shape, so the payload
keys below match that interface field-for-field. The `to_redacted` value must
already be redacted by the caller — a raw address must never reach this layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

NotificationEventName = Literal["notification.message.sent"]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class DomainEvent:
    """Matches the TS `DomainEventEnvelope` shape 1:1.

    `occurred_at` is kept as a timezone-aware `datetime` (not an ISO string as
    in the earlier services) because this event is persisted to the
    `outbox_event` table, whose `occurred_at` is a `timestamptz`. `to_dict`
    serializes it to ISO-8601 for the wire.
    """

    event_name: NotificationEventName
    tenant_id: UUID
    payload: dict[str, Any]
    actor_id: UUID | None = None
    event_version: int = 1
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_now)
    correlation_id: UUID | None = None
    causation_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": str(self.event_id),
            "eventName": self.event_name,
            "eventVersion": self.event_version,
            "tenantId": str(self.tenant_id),
            "actorId": str(self.actor_id) if self.actor_id else None,
            "occurredAt": self.occurred_at.isoformat(),
            "correlationId": str(self.correlation_id) if self.correlation_id else None,
            "causationId": str(self.causation_id) if self.causation_id else None,
            "payload": self.payload,
        }


def message_sent(
    tenant_id: UUID,
    *,
    notification_id: UUID,
    channel: str,
    template: str,
    to_redacted: str,
    actor_id: UUID | None = None,
) -> DomainEvent:
    """Keys mirror `NotificationSentPayload` in packages/types/src/events.ts."""
    return DomainEvent(
        event_name="notification.message.sent",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "notificationId": str(notification_id),
            "channel": channel,
            "template": template,
            "toRedacted": to_redacted,
        },
    )
