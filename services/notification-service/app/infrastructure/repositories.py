"""Concrete SQLAlchemy adapters for the domain repository ports.

Map ORM rows to domain entities at the boundary, so nothing above the
infrastructure layer ever holds a SQLAlchemy object.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.events import DomainEvent
from app.domain.models import NotificationMessage, NotificationTemplate
from app.infrastructure.models import (
    NotificationMessageORM,
    NotificationTemplateORM,
    OutboxEventORM,
)


def _ensure_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime read back from the DB to aware UTC.

    SQLite (the test harness) stores no timezone, so values come back naive and
    would compare/serialize incorrectly against `datetime.now(UTC)`.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _message_to_domain(row: NotificationMessageORM) -> NotificationMessage:
    return NotificationMessage(
        id=row.id,
        tenant_id=row.tenant_id,
        channel=row.channel,
        recipient=row.recipient,
        to_redacted=row.to_redacted,
        template_name=row.template_name,
        subject=row.subject,
        body=row.body,
        status=row.status,
        provider=row.provider,
        provider_message_id=row.provider_message_id,
        error_message=row.error_message,
        reference_kind=row.reference_kind,
        reference_id=row.reference_id,
        idempotency_key=row.idempotency_key,
        created_at=_ensure_utc(row.created_at),
        sent_at=_ensure_utc(row.sent_at),
        updated_at=_ensure_utc(row.updated_at),
    )


def _template_to_domain(row: NotificationTemplateORM) -> NotificationTemplate:
    return NotificationTemplate(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        channel=row.channel,
        subject_template=row.subject_template,
        body_template=row.body_template,
        created_at=_ensure_utc(row.created_at),
        updated_at=_ensure_utc(row.updated_at),
    )


class SqlAlchemyNotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_message(self, message: NotificationMessage) -> NotificationMessage:
        row = NotificationMessageORM(
            tenant_id=message.tenant_id,
            channel=message.channel,
            recipient=message.recipient,
            to_redacted=message.to_redacted,
            template_name=message.template_name,
            subject=message.subject,
            body=message.body,
            status=message.status,
            provider=message.provider,
            provider_message_id=message.provider_message_id,
            error_message=message.error_message,
            reference_kind=message.reference_kind,
            reference_id=message.reference_id,
            idempotency_key=message.idempotency_key,
        )
        self.session.add(row)
        self.session.flush()
        return _message_to_domain(row)

    def update_message(self, message: NotificationMessage) -> NotificationMessage:
        row = self.session.scalar(
            select(NotificationMessageORM).where(
                NotificationMessageORM.id == message.id,
                NotificationMessageORM.tenant_id == message.tenant_id,
            )
        )
        if row is None:
            raise LookupError(f"notification '{message.id}' not found for update")
        row.status = message.status
        row.provider = message.provider
        row.provider_message_id = message.provider_message_id
        row.error_message = message.error_message
        row.sent_at = message.sent_at
        self.session.flush()
        return _message_to_domain(row)

    def get_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: str
    ) -> NotificationMessage | None:
        row = self.session.scalar(
            select(NotificationMessageORM).where(
                NotificationMessageORM.tenant_id == tenant_id,
                NotificationMessageORM.idempotency_key == idempotency_key,
            )
        )
        return _message_to_domain(row) if row else None

    def get_message(self, tenant_id: UUID, message_id: UUID) -> NotificationMessage | None:
        row = self.session.scalar(
            select(NotificationMessageORM).where(
                NotificationMessageORM.id == message_id,
                NotificationMessageORM.tenant_id == tenant_id,
            )
        )
        return _message_to_domain(row) if row else None

    def list_messages(self, tenant_id: UUID, limit: int = 50) -> list[NotificationMessage]:
        stmt = (
            select(NotificationMessageORM)
            .where(NotificationMessageORM.tenant_id == tenant_id)
            .order_by(NotificationMessageORM.created_at.desc())
            .limit(limit)
        )
        return [_message_to_domain(row) for row in self.session.scalars(stmt).all()]

    def save_template(self, template: NotificationTemplate) -> NotificationTemplate:
        """Upsert by (tenant_id, name, channel) — the table's unique key."""
        row = self.session.scalar(
            select(NotificationTemplateORM).where(
                NotificationTemplateORM.tenant_id == template.tenant_id,
                NotificationTemplateORM.name == template.name,
                NotificationTemplateORM.channel == template.channel,
            )
        )
        if row is None:
            row = NotificationTemplateORM(
                tenant_id=template.tenant_id,
                name=template.name,
                channel=template.channel,
                subject_template=template.subject_template,
                body_template=template.body_template,
            )
            self.session.add(row)
        else:
            row.subject_template = template.subject_template
            row.body_template = template.body_template
        self.session.flush()
        return _template_to_domain(row)

    def get_template(
        self, tenant_id: UUID, name: str, channel: str
    ) -> NotificationTemplate | None:
        row = self.session.scalar(
            select(NotificationTemplateORM).where(
                NotificationTemplateORM.tenant_id == tenant_id,
                NotificationTemplateORM.name == name,
                NotificationTemplateORM.channel == channel,
            )
        )
        return _template_to_domain(row) if row else None

    def list_templates(self, tenant_id: UUID) -> list[NotificationTemplate]:
        stmt = (
            select(NotificationTemplateORM)
            .where(NotificationTemplateORM.tenant_id == tenant_id)
            .order_by(NotificationTemplateORM.name, NotificationTemplateORM.channel)
        )
        return [_template_to_domain(row) for row in self.session.scalars(stmt).all()]


class SqlAlchemyOutboxRepository:
    """Appends domain events to `outbox_event` on the same session — so an event
    and the state change that produced it commit atomically (conventions §4)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: DomainEvent) -> None:
        self.session.add(
            OutboxEventORM(
                event_id=event.event_id,
                tenant_id=event.tenant_id,
                event_name=event.event_name,
                event_version=event.event_version,
                payload=event.payload,
                actor_id=event.actor_id,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
            )
        )
        self.session.flush()

    def fetch_unprocessed(self, limit: int = 50) -> list[OutboxEventORM]:
        stmt = (
            select(OutboxEventORM)
            .where(OutboxEventORM.processed_at.is_(None))
            .order_by(OutboxEventORM.occurred_at)
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def mark_processed(self, event_ids: list[UUID]) -> None:
        if not event_ids:
            return
        now = datetime.now(UTC)
        for eid in event_ids:
            row = self.session.get(OutboxEventORM, eid)
            if row is not None and row.processed_at is None:
                row.processed_at = now
        self.session.flush()
