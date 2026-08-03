"""HTTP routes. Trusts the API Gateway's identity headers (x-tenant-id,
x-user-id) — the gateway already verified the JWT (see apps/api-gateway),
so this service never decodes tokens itself.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.application import services
from app.domain.errors import (
    ConnectionAlreadyExistsError,
    ConnectionInactiveError,
    ConnectionNotFoundError,
    SyncLogNotFoundError,
    WebhookNotFoundError,
)
from app.infrastructure.db import tenant_session
from app.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyConnectionRepository,
    SqlAlchemySyncLogRepository,
    SqlAlchemyWebhookRepository,
)
from app.interface.schemas import (
    ActivateConnectionRequest,
    CompleteSyncRequest,
    ConnectionListResponse,
    ConnectionResponse,
    CreateConnectionRequest,
    CreateWebhookRequest,
    StartSyncRequest,
    SyncLogListResponse,
    SyncLogResponse,
    WebhookListResponse,
    WebhookResponse,
)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


def _require_tenant(x_tenant_id: str | None) -> UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _require_user(x_user_id: str | None) -> UUID | None:
    if not x_user_id:
        return None
    try:
        return UUID(x_user_id)
    except ValueError:
        return None


def _conn_response(conn: object) -> ConnectionResponse:
    return ConnectionResponse(**conn.__dict__)


# ── Connection endpoints ───────────────────────────────────────────────────


@router.post("/connections", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(
    body: CreateConnectionRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> ConnectionResponse:
    tenant_id = _require_tenant(x_tenant_id)
    user_id = _require_user(x_user_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyConnectionRepository(s)
        try:
            conn, _event = services.create_connection(
                repo,
                tenant_id=tenant_id,
                provider=body.provider,
                display_name=body.display_name,
                created_by=user_id,
            )
        except ConnectionAlreadyExistsError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return _conn_response(conn)


@router.get("/connections", response_model=ConnectionListResponse)
def list_connections(
    x_tenant_id: str | None = Header(default=None),
) -> ConnectionListResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyConnectionRepository(s)
        items = services.list_connections(repo, tenant_id=tenant_id)
        return ConnectionListResponse(
            items=[_conn_response(c) for c in items],
            total=len(items),
        )


@router.get("/connections/{connection_id}", response_model=ConnectionResponse)
def get_connection(
    connection_id: UUID,
    x_tenant_id: str | None = Header(default=None),
) -> ConnectionResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyConnectionRepository(s)
        try:
            conn = services.get_connection(repo, tenant_id=tenant_id, connection_id=connection_id)
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        return _conn_response(conn)


@router.post(
    "/connections/{connection_id}/activate",
    response_model=ConnectionResponse,
)
def activate_connection(
    connection_id: UUID,
    body: ActivateConnectionRequest,
    x_tenant_id: str | None = Header(default=None),
) -> ConnectionResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyConnectionRepository(s)
        try:
            conn, _event = services.activate_connection(
                repo,
                tenant_id=tenant_id,
                connection_id=connection_id,
                access_token_encrypted=body.access_token_encrypted,
                refresh_token_encrypted=body.refresh_token_encrypted,
                token_expires_at=body.token_expires_at,
                external_account_id=body.external_account_id,
                scopes=body.scopes,
            )
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        return _conn_response(conn)


@router.post(
    "/connections/{connection_id}/revoke",
    response_model=ConnectionResponse,
)
def revoke_connection(
    connection_id: UUID,
    x_tenant_id: str | None = Header(default=None),
) -> ConnectionResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        conn_repo = SqlAlchemyConnectionRepository(s)
        wh_repo = SqlAlchemyWebhookRepository(s)
        try:
            conn, _event = services.revoke_connection(
                conn_repo,
                wh_repo,
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        return _conn_response(conn)


# ── Webhook endpoints ─────────────────────────────────────────────────────


@router.post(
    "/connections/{connection_id}/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_webhook(
    connection_id: UUID,
    body: CreateWebhookRequest,
    x_tenant_id: str | None = Header(default=None),
) -> WebhookResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        conn_repo = SqlAlchemyConnectionRepository(s)
        wh_repo = SqlAlchemyWebhookRepository(s)
        try:
            wh = services.create_webhook(
                conn_repo,
                wh_repo,
                tenant_id=tenant_id,
                connection_id=connection_id,
                target_url=body.target_url,
                event_types=body.event_types,
                secret=body.secret,
            )
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        except ConnectionInactiveError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return WebhookResponse(**wh.__dict__)


@router.get(
    "/connections/{connection_id}/webhooks",
    response_model=WebhookListResponse,
)
def list_webhooks(
    connection_id: UUID,
    x_tenant_id: str | None = Header(default=None),
) -> WebhookListResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        wh_repo = SqlAlchemyWebhookRepository(s)
        items = services.list_webhooks(wh_repo, tenant_id=tenant_id, connection_id=connection_id)
        return WebhookListResponse(
            items=[WebhookResponse(**wh.__dict__) for wh in items],
            total=len(items),
        )


@router.post(
    "/webhooks/{webhook_id}/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_webhook(
    webhook_id: UUID,
    x_tenant_id: str | None = Header(default=None),
) -> None:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        wh_repo = SqlAlchemyWebhookRepository(s)
        try:
            services.deactivate_webhook(wh_repo, tenant_id=tenant_id, webhook_id=webhook_id)
        except WebhookNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found") from exc


# ── Sync log endpoints ────────────────────────────────────────────────────


@router.post(
    "/connections/{connection_id}/sync",
    response_model=SyncLogResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_sync(
    connection_id: UUID,
    body: StartSyncRequest,
    x_tenant_id: str | None = Header(default=None),
) -> SyncLogResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        conn_repo = SqlAlchemyConnectionRepository(s)
        sync_repo = SqlAlchemySyncLogRepository(s)
        try:
            log = services.start_sync(
                conn_repo,
                sync_repo,
                tenant_id=tenant_id,
                connection_id=connection_id,
                direction=body.direction,
                entity_type=body.entity_type,
                entity_id=body.entity_id,
                request_payload=body.request_payload,
            )
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        except ConnectionInactiveError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return SyncLogResponse(**log.__dict__)


@router.post(
    "/sync/{sync_log_id}/complete",
    response_model=SyncLogResponse,
)
def complete_sync(
    sync_log_id: UUID,
    body: CompleteSyncRequest,
    x_tenant_id: str | None = Header(default=None),
) -> SyncLogResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        sync_repo = SqlAlchemySyncLogRepository(s)
        try:
            log, _event = services.complete_sync(
                sync_repo,
                tenant_id=tenant_id,
                sync_log_id=sync_log_id,
                status=body.status,
                external_id=body.external_id,
                error_message=body.error_message,
                response_payload=body.response_payload,
            )
        except SyncLogNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "sync log not found") from exc
        return SyncLogResponse(**log.__dict__)


@router.get(
    "/connections/{connection_id}/sync",
    response_model=SyncLogListResponse,
)
def list_sync_logs(
    connection_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None),
) -> SyncLogListResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        sync_repo = SqlAlchemySyncLogRepository(s)
        items = services.list_sync_logs(
            sync_repo,
            tenant_id=tenant_id,
            connection_id=connection_id,
            limit=limit,
        )
        return SyncLogListResponse(
            items=[SyncLogResponse(**log.__dict__) for log in items],
            total=len(items),
        )
