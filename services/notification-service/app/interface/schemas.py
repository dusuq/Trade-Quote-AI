"""Pydantic DTOs for the Notification service HTTP surface.

Responses expose only the **redacted** recipient (`to_redacted`), never the raw
address — the plain value lives only in the DB (M22 plan §PII Redaction).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.models import NotificationMessage, NotificationTemplate


class SendNotificationRequest(BaseModel):
    channel: str = Field(description="'email' or 'sms'")
    recipient: str = Field(min_length=1, max_length=320)
    template_name: str = Field(min_length=1, max_length=64)
    template_vars: dict[str, str] = Field(default_factory=dict)
    reference_kind: str | None = Field(default=None, max_length=16)
    reference_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=64)


class NotificationMessageResponse(BaseModel):
    id: UUID
    channel: str
    to_redacted: str
    template_name: str
    subject: str | None
    status: str
    provider: str | None
    provider_message_id: str | None
    error_message: str | None
    reference_kind: str | None
    reference_id: UUID | None
    created_at: datetime | None
    sent_at: datetime | None


class TemplateUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    channel: str = Field(description="'email' or 'sms'")
    subject_template: str | None = Field(default=None, max_length=1_000)
    body_template: str = Field(min_length=1, max_length=20_000)


class TemplateResponse(BaseModel):
    id: UUID | None
    name: str
    channel: str
    subject_template: str | None
    body_template: str
    created_at: datetime | None
    updated_at: datetime | None


def to_message_response(message: NotificationMessage) -> NotificationMessageResponse:
    if message.id is None:
        raise ValueError("message.id must not be None after persistence")
    return NotificationMessageResponse(
        id=message.id,
        channel=message.channel,
        to_redacted=message.to_redacted,
        template_name=message.template_name,
        subject=message.subject,
        status=message.status,
        provider=message.provider,
        provider_message_id=message.provider_message_id,
        error_message=message.error_message,
        reference_kind=message.reference_kind,
        reference_id=message.reference_id,
        created_at=message.created_at,
        sent_at=message.sent_at,
    )


def to_template_response(template: NotificationTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=template.id,
        name=template.name,
        channel=template.channel,
        subject_template=template.subject_template,
        body_template=template.body_template,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )
