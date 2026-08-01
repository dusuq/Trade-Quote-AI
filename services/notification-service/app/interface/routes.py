"""HTTP routes for the Notification service.

Trusts the gateway's `x-tenant-id`/`x-user-id` headers and never decodes a JWT
(conventions §1).

`POST /send` returns **202 Accepted** the moment the message is queued, then
does the provider call in a FastAPI BackgroundTask (M22 plan Q2) so a slow
SendGrid/Twilio call never hangs the caller's proposal-send workflow. The
background task opens its own `tenant_session`: the request's transaction has
already committed and closed by the time it runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status

from app.application.send_notification import SendNotificationUseCase
from app.domain.errors import (
    InvalidRecipientError,
    NotificationDeliveryError,
    TemplateNotFoundError,
    UnsupportedChannelError,
)
from app.domain.events import message_sent
from app.domain.models import Channel, MessageStatus, NotificationMessage, NotificationTemplate
from app.infrastructure.db import tenant_session
from app.infrastructure.repositories import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyOutboxRepository,
)
from app.interface.deps import deps
from app.interface.schemas import (
    NotificationMessageResponse,
    SendNotificationRequest,
    TemplateResponse,
    TemplateUpsertRequest,
    to_message_response,
    to_template_response,
)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _optional_actor(x_user_id: str | None) -> uuid.UUID | None:
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return None


def _use_case(session) -> SendNotificationUseCase:
    return SendNotificationUseCase(
        SqlAlchemyNotificationRepository(session),
        deps.email_provider(),
        deps.sms_provider(),
        SqlAlchemyOutboxRepository(session),
    )


def _dispatch(message: NotificationMessage) -> tuple[str, str]:
    """Call the channel's provider; return (provider_message_id, provider_name)."""
    if message.channel == Channel.EMAIL.value:
        email_provider = deps.email_provider()
        provider_id = email_provider.send_email(
            message.recipient, message.subject or "", message.body
        )
        return provider_id, getattr(email_provider, "name", "email")
    sms_provider = deps.sms_provider()
    provider_id = sms_provider.send_sms(message.recipient, message.body)
    return provider_id, getattr(sms_provider, "name", "sms")


def _deliver_in_background(
    tenant_id: uuid.UUID, message_id: uuid.UUID, actor_id: uuid.UUID | None
) -> None:
    """Three-phase delivery (ADR-0003 rule 3).

    Phase 1: short read txn — fetch the queued message.
    Phase 2: provider call unwrapped — no DB connection held.
    Phase 3: short write txn — status + outbox commit together (conventions §4).
    """
    # Phase 1: read
    with tenant_session(tenant_id) as session:
        repo = SqlAlchemyNotificationRepository(session)
        message = repo.get_message(tenant_id, message_id)
    if message is None or message.status != MessageStatus.QUEUED.value:
        return

    # Phase 2: provider call (NO open transaction)
    try:
        provider_message_id, provider_name = _dispatch(message)
    except NotificationDeliveryError as exc:
        # Phase 3a: record failure
        with tenant_session(tenant_id) as session:
            repo = SqlAlchemyNotificationRepository(session)
            message.status = MessageStatus.FAILED.value
            message.error_message = str(exc)
            repo.update_message(message)
        return

    # Phase 3b: record success + emit outbox event
    message.status = MessageStatus.SENT.value
    message.provider = provider_name
    message.provider_message_id = provider_message_id
    message.sent_at = datetime.now(UTC)
    with tenant_session(tenant_id) as session:
        repo = SqlAlchemyNotificationRepository(session)
        updated = repo.update_message(message)
        SqlAlchemyOutboxRepository(session).add(
            message_sent(
                tenant_id,
                notification_id=updated.id or message_id,
                channel=updated.channel,
                template=updated.template_name,
                to_redacted=updated.to_redacted,
                actor_id=actor_id,
            )
        )


@router.post(
    "/send",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=NotificationMessageResponse,
)
def send_notification(
    body: SendNotificationRequest,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> NotificationMessageResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    try:
        with tenant_session(tenant_id) as session:
            repo = SqlAlchemyNotificationRepository(session)
            if body.idempotency_key:
                existing = repo.get_by_idempotency_key(tenant_id, body.idempotency_key)
                if existing is not None:
                    return to_message_response(existing)
            message = _use_case(session).queue(
                tenant_id=tenant_id,
                channel=body.channel,
                recipient=body.recipient,
                template_name=body.template_name,
                template_vars=body.template_vars,
                reference_kind=body.reference_kind,
                reference_id=body.reference_id,
                idempotency_key=body.idempotency_key,
            )
    except (UnsupportedChannelError, InvalidRecipientError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except TemplateNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if message.id is None:
        raise ValueError("message.id must not be None after persistence")
    background_tasks.add_task(_deliver_in_background, tenant_id, message.id, actor_id)
    return to_message_response(message)


@router.get("/logs", response_model=list[NotificationMessageResponse])
def list_logs(
    limit: int = Query(default=50, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None),
) -> list[NotificationMessageResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        messages = SqlAlchemyNotificationRepository(session).list_messages(tenant_id, limit=limit)
        return [to_message_response(m) for m in messages]


@router.get("/logs/{message_id}", response_model=NotificationMessageResponse)
def get_log(
    message_id: uuid.UUID,
    x_tenant_id: str | None = Header(default=None),
) -> NotificationMessageResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        message = SqlAlchemyNotificationRepository(session).get_message(tenant_id, message_id)
        if message is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
        return to_message_response(message)


@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def upsert_template(
    body: TemplateUpsertRequest,
    x_tenant_id: str | None = Header(default=None),
) -> TemplateResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        saved = SqlAlchemyNotificationRepository(session).save_template(
            NotificationTemplate(
                id=None,
                tenant_id=tenant_id,
                name=body.name,
                channel=body.channel,
                subject_template=body.subject_template,
                body_template=body.body_template,
            )
        )
        return to_template_response(saved)


@router.get("/templates", response_model=list[TemplateResponse])
def list_templates(
    x_tenant_id: str | None = Header(default=None),
) -> list[TemplateResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        templates = SqlAlchemyNotificationRepository(session).list_templates(tenant_id)
        return [to_template_response(t) for t in templates]
