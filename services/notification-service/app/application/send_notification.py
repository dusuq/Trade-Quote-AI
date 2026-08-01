"""Use case: render a template and dispatch a notification.

`queue()` runs inside the request: it validates, renders, and persists a
`queued` ledger row, then returns so the route can reply 202 immediately.

Delivery then runs in a FastAPI BackgroundTask, split across three phases —
`load_for_delivery()`, the module-level `dispatch()`, and `record_sent()` /
`record_failure()`. They are separate because the provider call must happen
with no database connection held (ADR-0003 rule 3), which one method holding
one session cannot do. The route sequences them; the decisions live here.

Everything depends only on ports, so the whole thing is testable with fakes.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from app.application import templates_defaults
from app.application.render import render
from app.domain.errors import (
    InvalidRecipientError,
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

    # ── Delivery, phase by phase (ADR-0003 rule 3) ────────────────────────────
    #
    # Delivery spans three transactions, so it cannot be one method holding one
    # session: the provider call must happen with no connection held. The
    # transaction boundaries therefore live in the route (the same shape as
    # ai-service's `_run_metered`), but every decision lives here — so there is
    # one implementation of "should this send?" and "what does sent mean?", and
    # the tests for it cover the code that actually runs.

    def load_for_delivery(
        self, *, tenant_id: UUID, message_id: UUID
    ) -> NotificationMessage | None:
        """Phase 1 (short read txn). None means there is nothing to send.

        Returning None rather than raising for a missing row is deliberate:
        this runs in a BackgroundTask after the 202, where there is no caller
        left to receive an exception.
        """
        message = self._repo.get_message(tenant_id, message_id)
        if message is None:
            return None
        # Idempotent: a re-fired background task must not double-send.
        if message.status != MessageStatus.QUEUED.value:
            return None
        return message

    def record_sent(
        self,
        *,
        tenant_id: UUID,
        message: NotificationMessage,
        provider_message_id: str,
        provider_name: str,
        actor_id: UUID | None = None,
    ) -> NotificationMessage:
        """Phase 3 (short write txn) — status **and** outbox event together.

        Both are writes on the one session, so `tenant_session` commits them
        atomically (conventions §4): the event cannot exist without the status,
        and the status cannot exist unpublished.
        """
        message.status = MessageStatus.SENT.value
        message.provider = provider_name
        message.provider_message_id = provider_message_id
        message.sent_at = datetime.now(UTC)
        updated = self._repo.update_message(message)

        notification_id = updated.id or message.id
        if notification_id is None:
            # Unreachable via load_for_delivery, which only returns persisted
            # rows. Explicit rather than an assert, which `python -O` strips.
            raise ValueError("cannot record delivery for an unpersisted message")

        self._outbox.add(
            message_sent(
                tenant_id,
                notification_id=notification_id,
                channel=updated.channel,
                template=updated.template_name,
                to_redacted=updated.to_redacted,
                actor_id=actor_id,
            )
        )
        return updated

    def record_failure(
        self, *, message: NotificationMessage, error: Exception
    ) -> NotificationMessage:
        """Phase 3a (short write txn) — a failed send is still a ledger fact.

        No outbox event: nothing was sent, so there is nothing to tell anyone.
        """
        message.status = MessageStatus.FAILED.value
        message.error_message = str(error)
        return self._repo.update_message(message)


def dispatch(
    message: NotificationMessage,
    *,
    email_provider: EmailProvider,
    sms_provider: SmsProvider,
) -> tuple[str, str]:
    """Phase 2 — the provider call. Returns (provider_message_id, provider_name).

    A module-level function, not a method, because this phase must run with
    **no database session open at all** (ADR-0003 rule 3) — and a function that
    takes only providers cannot accidentally be handed a repository.

    Raises `NotificationDeliveryError` on provider failure.
    """
    if message.channel == Channel.EMAIL.value:
        provider_id = email_provider.send_email(
            message.recipient, message.subject or "", message.body
        )
        return provider_id, getattr(email_provider, "name", "email")
    # Only email and sms reach here — queue() rejected everything else.
    provider_id = sms_provider.send_sms(message.recipient, message.body)
    return provider_id, getattr(sms_provider, "name", "sms")
