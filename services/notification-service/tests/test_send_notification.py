"""SendNotificationUseCase: queue + deliver, against in-memory fakes."""

from __future__ import annotations

import uuid

import pytest

from app.application.send_notification import SendNotificationUseCase
from app.domain.errors import (
    InvalidRecipientError,
    NotificationNotFoundError,
    TemplateNotFoundError,
    UnsupportedChannelError,
)
from app.domain.models import MessageStatus, NotificationTemplate
from tests.fakes import (
    FakeEmailProvider,
    FakeSmsProvider,
    InMemoryNotificationRepository,
    InMemoryOutboxRepository,
)

TENANT = uuid.uuid4()
ACTOR = uuid.uuid4()


def _use_case(*, email=None, sms=None, repo=None, outbox=None):
    repo = repo or InMemoryNotificationRepository()
    outbox = outbox or InMemoryOutboxRepository()
    uc = SendNotificationUseCase(
        repo, email or FakeEmailProvider(), sms or FakeSmsProvider(), outbox
    )
    return uc, repo, outbox


def test_queue_renders_default_template_and_saves_queued() -> None:
    uc, repo, _ = _use_case()

    msg = uc.queue(
        tenant_id=TENANT,
        channel="email",
        recipient="jane@domain.com",
        template_name="quote_delivery",
        template_vars={"company_name": "ACME", "customer_name": "Jane", "view_link": "http://x"},
    )

    assert msg.id is not None
    assert msg.status == MessageStatus.QUEUED.value
    assert msg.subject == "Your quote from ACME"
    assert "Jane" in msg.body
    assert msg.to_redacted == "j***e@domain.com"
    assert repo.messages[msg.id].recipient == "jane@domain.com"  # plaintext only in the store


def test_queue_prefers_a_custom_tenant_template() -> None:
    repo = InMemoryNotificationRepository()
    repo.save_template(
        NotificationTemplate(
            id=None,
            tenant_id=TENANT,
            name="quote_delivery",
            channel="sms",
            subject_template=None,
            body_template="Custom: {{ company_name }}",
        )
    )
    uc, _, _ = _use_case(repo=repo)

    msg = uc.queue(
        tenant_id=TENANT,
        channel="sms",
        recipient="+14155552671",
        template_name="quote_delivery",
        template_vars={"company_name": "ACME"},
    )

    assert msg.body == "Custom: ACME"


def test_queue_rejects_unknown_channel() -> None:
    uc, _, _ = _use_case()
    with pytest.raises(UnsupportedChannelError):
        uc.queue(tenant_id=TENANT, channel="carrier-pigeon", recipient="x", template_name="quote_delivery")


def test_queue_rejects_undeliverable_channel() -> None:
    uc, _, _ = _use_case()
    with pytest.raises(UnsupportedChannelError):
        uc.queue(tenant_id=TENANT, channel="push", recipient="tok", template_name="quote_delivery")


def test_queue_validates_recipient_shape() -> None:
    uc, _, _ = _use_case()
    with pytest.raises(InvalidRecipientError):
        uc.queue(tenant_id=TENANT, channel="email", recipient="no-at-sign", template_name="quote_delivery")
    with pytest.raises(InvalidRecipientError):
        uc.queue(tenant_id=TENANT, channel="sms", recipient="4155552671", template_name="quote_delivery")


def test_queue_unknown_template_raises() -> None:
    uc, _, _ = _use_case()
    with pytest.raises(TemplateNotFoundError):
        uc.queue(tenant_id=TENANT, channel="email", recipient="a@b.com", template_name="nope")


def test_deliver_email_marks_sent_and_emits_outbox_event() -> None:
    email = FakeEmailProvider()
    uc, _repo, outbox = _use_case(email=email)
    msg = uc.queue(
        tenant_id=TENANT,
        channel="email",
        recipient="jane@domain.com",
        template_name="quote_delivery",
        template_vars={"company_name": "ACME", "view_link": "http://x"},
    )

    delivered = uc.deliver(tenant_id=TENANT, message_id=msg.id, actor_id=ACTOR)

    assert delivered.status == MessageStatus.SENT.value
    assert delivered.provider_message_id is not None
    assert delivered.sent_at is not None
    assert len(email.sent) == 1
    # Exactly one outbox event, canonical name + redacted recipient only.
    assert len(outbox.events) == 1
    event = outbox.events[0]
    assert event.event_name == "notification.message.sent"
    assert event.payload["toRedacted"] == "j***e@domain.com"
    assert event.payload["channel"] == "email"
    assert "jane@domain.com" not in str(event.to_dict())  # no plaintext leak


def test_deliver_sms_uses_sms_provider() -> None:
    sms = FakeSmsProvider()
    uc, _, _ = _use_case(sms=sms)
    msg = uc.queue(
        tenant_id=TENANT,
        channel="sms",
        recipient="+14155552671",
        template_name="quote_delivery",
        template_vars={"company_name": "ACME", "view_link": "http://x"},
    )
    uc.deliver(tenant_id=TENANT, message_id=msg.id)
    assert len(sms.sent) == 1


def test_deliver_failure_marks_failed_and_no_event() -> None:
    uc, _, outbox = _use_case(email=FakeEmailProvider(fail=True))
    msg = uc.queue(
        tenant_id=TENANT,
        channel="email",
        recipient="jane@domain.com",
        template_name="quote_delivery",
        template_vars={"company_name": "ACME"},
    )

    delivered = uc.deliver(tenant_id=TENANT, message_id=msg.id)

    assert delivered.status == MessageStatus.FAILED.value
    assert delivered.error_message
    assert outbox.events == []  # a failed send emits no sent event


def test_deliver_is_idempotent() -> None:
    email = FakeEmailProvider()
    uc, _, outbox = _use_case(email=email)
    msg = uc.queue(
        tenant_id=TENANT,
        channel="email",
        recipient="jane@domain.com",
        template_name="quote_delivery",
        template_vars={"company_name": "ACME"},
    )
    uc.deliver(tenant_id=TENANT, message_id=msg.id)
    uc.deliver(tenant_id=TENANT, message_id=msg.id)  # re-fired task

    assert len(email.sent) == 1  # not double-sent
    assert len(outbox.events) == 1


def test_deliver_missing_message_raises() -> None:
    uc, _, _ = _use_case()
    with pytest.raises(NotificationNotFoundError):
        uc.deliver(tenant_id=TENANT, message_id=uuid.uuid4())
