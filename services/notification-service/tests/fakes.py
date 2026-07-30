"""In-memory fakes for every port.

No test needs credentials, a network, or a real provider SDK (conventions §3).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.domain.errors import NotificationDeliveryError
from app.domain.events import DomainEvent
from app.domain.models import NotificationMessage, NotificationTemplate


class FakeEmailProvider:
    name = "console"

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.sent: list[tuple[str, str, str]] = []

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        *,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> str:
        if self.fail:
            raise NotificationDeliveryError("simulated email failure")
        self.sent.append((to_email, subject, body))
        return f"fake-email-{uuid4()}"


class FakeSmsProvider:
    name = "console"

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    def send_sms(self, to_phone: str, body: str) -> str:
        if self.fail:
            raise NotificationDeliveryError("simulated sms failure")
        self.sent.append((to_phone, body))
        return f"fake-sms-{uuid4()}"


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self.messages: dict[UUID, NotificationMessage] = {}
        self.templates: dict[tuple[UUID, str, str], NotificationTemplate] = {}

    def save_message(self, message: NotificationMessage) -> NotificationMessage:
        message.id = message.id or uuid4()
        self.messages[message.id] = message
        return message

    def update_message(self, message: NotificationMessage) -> NotificationMessage:
        assert message.id is not None
        self.messages[message.id] = message
        return message

    def get_message(self, tenant_id: UUID, message_id: UUID) -> NotificationMessage | None:
        found = self.messages.get(message_id)
        if found is None or found.tenant_id != tenant_id:
            return None
        return found

    def list_messages(self, tenant_id: UUID, limit: int = 50) -> list[NotificationMessage]:
        return [m for m in self.messages.values() if m.tenant_id == tenant_id][:limit]

    def save_template(self, template: NotificationTemplate) -> NotificationTemplate:
        template.id = template.id or uuid4()
        self.templates[(template.tenant_id, template.name, template.channel)] = template
        return template

    def get_template(
        self, tenant_id: UUID, name: str, channel: str
    ) -> NotificationTemplate | None:
        return self.templates.get((tenant_id, name, channel))

    def list_templates(self, tenant_id: UUID) -> list[NotificationTemplate]:
        return [t for t in self.templates.values() if t.tenant_id == tenant_id]


class InMemoryOutboxRepository:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def add(self, event: DomainEvent) -> None:
        self.events.append(event)


class FakeDependencies:
    """Stands in for the composition root in route tests."""

    def __init__(self) -> None:
        self.email = FakeEmailProvider()
        self.sms = FakeSmsProvider()

    def email_provider(self):
        return self.email

    def sms_provider(self):
        return self.sms
