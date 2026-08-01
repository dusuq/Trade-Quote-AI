"""Domain entities and value objects for the Notification service (M22 / T205).

Framework-free — no SQLAlchemy, no Pydantic, no provider SDK types (conventions
§3). Unlike most of this codebase's value objects these are **mutable**
(`slots=True`, not frozen): a message's status/provider_message_id/sent_at are
filled in by the delivery step after the row already exists, and the use case
mutates the entity in place before persisting the update.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class Channel(str, enum.Enum):
    """Delivery channels. Mirrors the `channel` union in packages/types
    (`NotificationSentPayload`). Only EMAIL and SMS have adapters today; the
    other two are reserved so the enum and the DB column don't need widening
    later."""

    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"


class MessageStatus(str, enum.Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


# Channels this service can actually deliver to right now.
DELIVERABLE_CHANNELS: frozenset[Channel] = frozenset({Channel.EMAIL, Channel.SMS})


@dataclass(slots=True)
class NotificationTemplate:
    id: UUID | None
    tenant_id: UUID
    name: str
    channel: str
    subject_template: str | None
    body_template: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class NotificationMessage:
    id: UUID | None
    tenant_id: UUID
    channel: str
    recipient: str
    to_redacted: str
    template_name: str
    subject: str | None
    body: str
    status: str
    provider: str | None = None
    provider_message_id: str | None = None
    error_message: str | None = None
    reference_kind: str | None = None
    reference_id: UUID | None = None
    idempotency_key: str | None = None
    created_at: datetime | None = None
    sent_at: datetime | None = None
    updated_at: datetime | None = None
