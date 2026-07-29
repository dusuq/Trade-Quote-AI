"""AI domain events — Python mirror of the canonical registry in
`packages/types` (see docs/03-DOMAIN-EVENTS.md).

`ai.quote.drafted` and `ai.usage.recorded` are already declared there with
their payload types; conventions §4 forbids inventing a local shape, so the
payload keys below match those interfaces field-for-field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

AiEventName = Literal["ai.quote.drafted", "ai.usage.recorded"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class DomainEvent:
    """Matches the TS `DomainEventEnvelope` shape 1:1."""

    event_name: AiEventName
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


def quote_drafted(
    tenant_id: UUID,
    *,
    quote_id: UUID,
    model_id: str,
    input_kind: str,
    tokens_used: int,
    actor_id: UUID | None = None,
) -> DomainEvent:
    """Keys mirror `AiQuoteDraftedPayload` in packages/types/src/events.ts."""
    return DomainEvent(
        event_name="ai.quote.drafted",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote_id),
            "modelId": model_id,
            "inputKind": input_kind,
            "tokensUsed": tokens_used,
        },
    )


def usage_recorded(
    tenant_id: UUID,
    *,
    feature: str,
    model_id: str,
    tokens_used: int,
    cost_minor: int,
    actor_id: UUID | None = None,
) -> DomainEvent:
    """Keys mirror `AiUsageRecordedPayload` in packages/types/src/events.ts."""
    return DomainEvent(
        event_name="ai.usage.recorded",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "feature": feature,
            "modelId": model_id,
            "tokensUsed": tokens_used,
            "costMinor": cost_minor,
        },
    )
