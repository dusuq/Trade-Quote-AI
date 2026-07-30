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

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status

from app.application.send_notification import SendNotificationUseCase
from app.domain.errors import (
    InvalidRecipientError,
    TemplateNotFoundError,
    UnsupportedChannelError,
)
from app.domain.models import NotificationTemplate
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


def _deliver_in_background(
    tenant_id: uuid.UUID, message_id: uuid.UUID, actor_id: uuid.UUID | None
) -> None:
    """Runs after the 202 response. Its own transaction so the status update and
    the outbox event commit together (conventions §4)."""
    with tenant_session(tenant_id) as session:
        _use_case(session).deliver(
            tenant_id=tenant_id, message_id=message_id, actor_id=actor_id
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
            message = _use_case(session).queue(
                tenant_id=tenant_id,
                channel=body.channel,
                recipient=body.recipient,
                template_name=body.template_name,
                template_vars=body.template_vars,
                reference_kind=body.reference_kind,
                reference_id=body.reference_id,
            )
    except (UnsupportedChannelError, InvalidRecipientError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except TemplateNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    # queue() persists the row, so the id is set — narrow it for the scheduler.
    assert message.id is not None
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
