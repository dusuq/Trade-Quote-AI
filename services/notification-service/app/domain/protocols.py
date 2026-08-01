"""Ports. The application layer depends only on these, never on a provider SDK,
`httpx`, or SQLAlchemy — so every use case runs against in-memory fakes with no
network, no credentials, and no database (conventions §3).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.domain.events import DomainEvent
from app.domain.models import NotificationMessage, NotificationTemplate


class EmailProvider(Protocol):
    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        *,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> str:
        """Send an email; return the provider's message id.

        Raises `NotificationDeliveryError` on any provider failure.
        """
        ...


class SmsProvider(Protocol):
    def send_sms(self, to_phone: str, body: str) -> str:
        """Send an SMS; return the provider's message id.

        Raises `NotificationDeliveryError` on any provider failure.
        """
        ...


class NotificationRepository(Protocol):
    def save_message(self, message: NotificationMessage) -> NotificationMessage: ...
    def update_message(self, message: NotificationMessage) -> NotificationMessage: ...
    def get_message(
        self, tenant_id: UUID, message_id: UUID
    ) -> NotificationMessage | None: ...
    def get_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: str
    ) -> NotificationMessage | None: ...
    def list_messages(self, tenant_id: UUID, limit: int = 50) -> list[NotificationMessage]: ...
    def save_template(self, template: NotificationTemplate) -> NotificationTemplate: ...
    def get_template(
        self, tenant_id: UUID, name: str, channel: str
    ) -> NotificationTemplate | None: ...
    def list_templates(self, tenant_id: UUID) -> list[NotificationTemplate]: ...


class OutboxRepository(Protocol):
    def add(self, event: DomainEvent) -> None:
        """Append an event to the transactional outbox (conventions §4)."""
        ...


class OutboxRelayStore(Protocol):
    """Cross-tenant reads of the outbox, for the relay only.

    Separate from `OutboxRepository` (ISP): writers append within one tenant's
    transaction; the relay reads across every tenant with no tenant context at
    all. Keeping them apart is also what stops a request-path caller from
    reaching the elevated cross-tenant read by accident.
    """

    def claim_unprocessed(self, limit: int) -> list[DomainEvent]:
        """Claim up to `limit` unpublished events, locking them for this txn."""
        ...

    def mark_processed(self, event_ids: Sequence[UUID]) -> int:
        """Mark events published. Returns how many were actually marked."""
        ...
