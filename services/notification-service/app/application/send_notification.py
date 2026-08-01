"""Use case: render a template and dispatch a notification.

Split into two phases so the HTTP request never blocks on a provider:

* `queue()` runs inside the request. It validates, renders, and persists a
  `queued` ledger row, then returns — the route replies 202 immediately.
* `deliver()` runs inside a FastAPI BackgroundTask (its own DB transaction). It
  calls the provider and writes the terminal status **and** the
  `notification.message.sent` outbox event in one transaction (conventions §4).

Both phases depend only on ports, so the whole thing is testable with fakes.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from app.application import templates_defaults
from app.application.render import render
from app.domain.errors import (
    InvalidRecipientError,
    NotificationDeliveryError,
    NotificationNotFoundError,
    TemplateNotFoundError,
    UnsupportedChannelError,
)
from app.domain.events import message_sent
from app.domain.models import (
    DELIVERABLE_CHANNELS,
    Channel,
    MessageStatus,
    NotificationMessage,
)
from app.domain.protocols import (
    EmailProvider,
    NotificationRepository,
    OutboxRepository,
    SmsProvider,
)
from app.domain.redact import redact_for_channel


def _parse_channel(channel: str) -> Channel:
    try:
        parsed = Channel(channel)
    except ValueError as exc:
        raise UnsupportedChannelError(f"unknown channel '{channel}'") from exc
    if parsed not in DELIVERABLE_CHANNELS:
        raise UnsupportedChannelError(
            f"channel '{channel}' has no delivery adapter yet (email and sms only)"
        )
    return parsed


def _validate_recipient(channel: Channel, recipient: str) -> None:
    value = recipient.strip()
    if not value:
        raise InvalidRecipientError("recipient is required")
    if channel is Channel.EMAIL and "@" not in value:
        raise InvalidRecipientError("email recipient must contain '@'")
    if channel is Channel.SMS and not value.startswith("+"):
        # E.164 keeps routing unambiguous; the gateway/UI collects it this way.
        raise InvalidRecipientError("sms recipient must be E.164 (start with '+')")


class SendNotificationUseCase:
    def __init__(
        self,
        repo: NotificationRepository,
        email_provider: EmailProvider,
        sms_provider: SmsProvider,
        outbox_repo: OutboxRepository,
    ) -> None:
        self._repo = repo
        self._email = email_provider
        self._sms = sms_provider
        self._outbox = outbox_repo

    def _resolve_template(
        self, tenant_id: UUID, name: str, channel: str
    ) -> tuple[str | None, str]:
        """Custom tenant template first, then the built-in default."""
        custom = self._repo.get_template(tenant_id, name, channel)
        if custom is not None:
            return custom.subject_template, custom.body_template
        default = templates_defaults.default_template(name, channel)
        if default is None:
            raise TemplateNotFoundError(
                f"no template '{name}' for channel '{channel}'"
            )
        return default

    def queue(
        self,
        *,
        tenant_id: UUID,
        channel: str,
        recipient: str,
        template_name: str,
        template_vars: Mapping[str, object] | None = None,
        reference_kind: str | None = None,
        reference_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> NotificationMessage:
        parsed_channel = _parse_channel(channel)
        _validate_recipient(parsed_channel, recipient)
        variables = dict(template_vars or {})

        subject_template, body_template = self._resolve_template(
            tenant_id, template_name, channel
        )
        is_email = parsed_channel is Channel.EMAIL
        subject = (
            render(subject_template, variables, html=False)
            if is_email and subject_template
            else None
        )
        body = render(body_template, variables, html=is_email)

        message = NotificationMessage(
            id=None,
            tenant_id=tenant_id,
            channel=channel,
            recipient=recipient.strip(),
            to_redacted=redact_for_channel(channel, recipient),
            template_name=template_name,
            subject=subject,
            body=body,
            status=MessageStatus.QUEUED.value,
            reference_kind=reference_kind,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
        )
        return self._repo.save_message(message)

    def deliver(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
        actor_id: UUID | None = None,
    ) -> NotificationMessage:
        message = self._repo.get_message(tenant_id, message_id)
        if message is None:
            raise NotificationNotFoundError(str(message_id))
        # Idempotent: a re-fired background task must not double-send.
        if message.status != MessageStatus.QUEUED.value:
            return message

        try:
            provider_message_id, provider_name = self._dispatch(message)
        except NotificationDeliveryError as exc:
            message.status = MessageStatus.FAILED.value
            message.error_message = str(exc)
            return self._repo.update_message(message)

        message.status = MessageStatus.SENT.value
        message.provider = provider_name
        message.provider_message_id = provider_message_id
        message.sent_at = datetime.now(UTC)
        updated = self._repo.update_message(message)

        # Status update + outbox event in the SAME transaction (conventions §4):
        # both are writes on this session, committed together by tenant_session.
        self._outbox.add(
            message_sent(
                tenant_id,
                notification_id=updated.id or message_id,
                channel=updated.channel,
                template=updated.template_name,
                to_redacted=updated.to_redacted,
                actor_id=actor_id,
            )
        )
        return updated

    def _dispatch(self, message: NotificationMessage) -> tuple[str, str]:
        """Send via the channel's provider; return (provider_message_id, provider_name)."""
        if message.channel == Channel.EMAIL.value:
            provider_id = self._email.send_email(
                message.recipient, message.subject or "", message.body
            )
            return provider_id, getattr(self._email, "name", "email")
        # Only email and sms reach here — queue() rejected everything else.
        provider_id = self._sms.send_sms(message.recipient, message.body)
        return provider_id, getattr(self._sms, "name", "sms")
