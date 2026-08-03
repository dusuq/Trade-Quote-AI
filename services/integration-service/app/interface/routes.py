"""HTTP routes. Trusts the API Gateway's identity headers (x-tenant-id,
x-user-id) — the gateway already verified the JWT (see apps/api-gateway),
so this service never decodes tokens itself.
"""

from __future__ import annotations

import dataclasses
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from app.application import services
from app.config import settings
from app.domain.entities import IntegrationConnection, ProviderKind, SyncLog, WebhookSubscription
from app.domain.errors import (
    ConnectionAlreadyExistsError,
    ConnectionInactiveError,
    ConnectionNotFoundError,
    OAuthStateInvalidError,
    ProviderAuthError,
    SyncLogNotFoundError,
    WebhookNotFoundError,
)
from app.domain.providers import InvoiceSyncClient, OAuthProvider
from app.infrastructure.crypto import FernetTokenCipher
from app.infrastructure.db import tenant_session
from app.infrastructure.providers.quickbooks import QuickBooksProvider
from app.infrastructure.providers.xero import XeroProvider
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
    PushInvoiceRequest,
    StartOAuthResponse,
    StartSyncRequest,
    SyncLogListResponse,
    SyncLogResponse,
    WebhookListResponse,
    WebhookResponse,
    ZapierConnectResponse,
)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])
# Mounted separately in app/main.py. Public and unauthenticated — the browser
# lands here straight from QuickBooks/Xero's own redirect, with no
# TradeQuote session at all (same trust model as esign-service's
# `/v1/sign/{token}`; see docs/07-SERVICE-CONVENTIONS.md and
# apps/api-gateway/src/plugins/auth.ts's PUBLIC_PATH_PATTERNS, which must
# allowlist these two exact paths).
public_router = APIRouter(prefix="/v1/integrations", tags=["integrations-oauth-callback"])

# One cipher instance for the process — constructing it validates the key
# eagerly (fails fast on a bad INTEGRATION_TOKEN_ENCRYPTION_KEY at import
# time rather than on the first token read). Same lifetime/reuse pattern as
# esign-service's module-level `_tenant_resolver`/`_proposal_reader`.
_cipher = FernetTokenCipher()

# Providers are stateless (settings-only) and cheap to construct — no pooled
# connection to share, unlike ServiceClient, so a fresh instance per call
# keeps this simple rather than introducing a shared-mutable-state seam.
_OAUTH_PROVIDERS: dict[str, OAuthProvider] = {
    "quickbooks": QuickBooksProvider(),
    "xero": XeroProvider(),
}
_SYNC_CLIENTS: dict[str, InvoiceSyncClient] = {
    "quickbooks": _OAUTH_PROVIDERS["quickbooks"],  # type: ignore[dict-item]
    "xero": _OAUTH_PROVIDERS["xero"],  # type: ignore[dict-item]
}


def _oauth_provider_for(provider: ProviderKind) -> OAuthProvider:
    resolved = _OAUTH_PROVIDERS.get(provider)
    if resolved is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{provider} has no OAuth flow (API-key/webhook based)"
        )
    return resolved


def _sync_client_for(provider: ProviderKind) -> InvoiceSyncClient:
    resolved = _SYNC_CLIENTS.get(provider)
    if resolved is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{provider} does not support invoice sync")
    return resolved


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


def _conn_response(conn: IntegrationConnection) -> ConnectionResponse:
    # `**conn.__dict__` doesn't exist to unpack: every domain entity is a
    # `@dataclass(slots=True)`, and slotted instances carry no `__dict__` —
    # `dataclasses.asdict` reads fields via reflection instead, which works
    # on slotted classes. Also filters out `access_token_encrypted` /
    # `refresh_token_encrypted` / `config_json`, which aren't part of
    # `ConnectionResponse` and must never reach an HTTP response body.
    return ConnectionResponse(**{f: v for f, v in dataclasses.asdict(conn).items() if f in ConnectionResponse.model_fields})


def _webhook_response(wh: WebhookSubscription) -> WebhookResponse:
    return WebhookResponse(**{f: v for f, v in dataclasses.asdict(wh).items() if f in WebhookResponse.model_fields})


def _sync_log_response(log: SyncLog) -> SyncLogResponse:
    return SyncLogResponse(**{f: v for f, v in dataclasses.asdict(log).items() if f in SyncLogResponse.model_fields})


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
                _cipher,
                tenant_id=tenant_id,
                connection_id=connection_id,
                access_token=body.access_token,
                refresh_token=body.refresh_token,
                token_expires_at=body.token_expires_at,
                external_account_id=body.external_account_id,
                scopes=body.scopes,
            )
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        return _conn_response(conn)


@router.post(
    "/connections/{connection_id}/oauth/start",
    response_model=StartOAuthResponse,
)
def start_oauth(
    connection_id: UUID,
    x_tenant_id: str | None = Header(default=None),
) -> StartOAuthResponse:
    """Return the QuickBooks/Xero authorize URL for a pending connection.
    The web UI redirects the browser to `authorize_url`; the provider then
    redirects back to this service's public callback route below."""
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyConnectionRepository(s)
        conn = repo.get(tenant_id, connection_id)
        if conn is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
        if conn.status != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"connection is {conn.status}, not pending"
            )
        oauth_provider = _oauth_provider_for(conn.provider)
        updated, authorize_url = services.start_oauth_connection(
            repo,
            oauth_provider,
            tenant_id=tenant_id,
            provider=conn.provider,
            display_name=conn.display_name,
            created_by=conn.created_by,
        )
        return StartOAuthResponse(connection=_conn_response(updated), authorize_url=authorize_url)


@router.post(
    "/connections/{connection_id}/zapier/connect",
    response_model=ZapierConnectResponse,
)
def connect_zapier(
    connection_id: UUID,
    x_tenant_id: str | None = Header(default=None),
) -> ZapierConnectResponse:
    """Activate a Zapier connection by minting a signing secret (Zapier is
    API-key/webhook based, not OAuth — see `services.connect_zapier`)."""
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyConnectionRepository(s)
        try:
            conn, secret = services.connect_zapier(
                repo, _cipher, tenant_id=tenant_id, connection_id=connection_id,
            )
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        except ConnectionInactiveError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return ZapierConnectResponse(connection=_conn_response(conn), api_key=secret)


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
        return _webhook_response(wh)


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
            items=[_webhook_response(wh) for wh in items],
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
        return _sync_log_response(log)


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
        return _sync_log_response(log)


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
            items=[_sync_log_response(log) for log in items],
            total=len(items),
        )


@router.post(
    "/connections/{connection_id}/sync/push",
    response_model=SyncLogResponse,
    status_code=status.HTTP_201_CREATED,
)
def push_invoice(
    connection_id: UUID,
    body: PushInvoiceRequest,
    x_tenant_id: str | None = Header(default=None),
) -> SyncLogResponse:
    """Push one quote/invoice to the connected QuickBooks/Xero account and
    record the outcome as a `SyncLog` — the real sync T308b adds on top of
    T308's connection-state-only scaffold. `POST /connections/{id}/sync` +
    `/sync/{id}/complete` remain for recording a sync performed elsewhere
    (e.g. a future async worker); this endpoint does the push itself,
    synchronously, end to end."""
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        conn_repo = SqlAlchemyConnectionRepository(s)
        sync_repo = SqlAlchemySyncLogRepository(s)
        conn = conn_repo.get(tenant_id, connection_id)
        if conn is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
        oauth_provider = _oauth_provider_for(conn.provider)
        sync_client = _sync_client_for(conn.provider)
        try:
            log, _event = services.push_invoice_sync(
                conn_repo,
                sync_repo,
                oauth_provider,
                sync_client,
                _cipher,
                tenant_id=tenant_id,
                connection_id=connection_id,
                entity_type=body.entity_type,
                entity_id=body.entity_id,
                payload=body.payload,
            )
        except ConnectionNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found") from exc
        except ConnectionInactiveError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return _sync_log_response(log)


# ── OAuth callback (public, unauthenticated) ────────────────────────────────
#
# The browser lands here straight from QuickBooks/Xero's own redirect — there
# is no gateway JWT, no `x-tenant-id` header, nothing but the query string the
# provider sends. `state` (opaque to the provider, minted by
# `services.start_oauth_connection`) is what authenticates this request
# instead — see `services.complete_oauth_callback` for why embedding
# tenant/connection ids in it is safe.


def _redirect_url(*, provider: str, connected: bool, message: str | None = None) -> str:
    params: dict[str, str] = {"provider": provider, "connected": "true" if connected else "false"}
    if message:
        params["error"] = message
    return f"{settings.web_app_url}/settings/integrations?{urlencode(params)}"


@public_router.get("/quickbooks/callback", include_in_schema=False)
def quickbooks_oauth_callback(request: Request) -> RedirectResponse:
    return _handle_oauth_callback("quickbooks", request)


@public_router.get("/xero/callback", include_in_schema=False)
def xero_oauth_callback(request: Request) -> RedirectResponse:
    return _handle_oauth_callback("xero", request)


def _handle_oauth_callback(provider: str, request: Request) -> RedirectResponse:
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")
    provider_error = params.get("error")
    if provider_error:
        return RedirectResponse(_redirect_url(provider=provider, connected=False, message=provider_error))
    if not code or not state:
        return RedirectResponse(
            _redirect_url(provider=provider, connected=False, message="missing code or state")
        )

    try:
        tenant_id_str = state.split(":", 1)[0]
        tenant_id = UUID(tenant_id_str)
    except (ValueError, IndexError):
        return RedirectResponse(
            _redirect_url(provider=provider, connected=False, message="invalid state")
        )

    oauth_provider = _OAUTH_PROVIDERS[provider]
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyConnectionRepository(s)
        try:
            services.complete_oauth_callback(
                repo,
                oauth_provider,
                _cipher,
                state=state,
                code=code,
                callback_params=params,
            )
        except (OAuthStateInvalidError, ConnectionNotFoundError):
            # Never distinguish "no such connection" from "state mismatch" —
            # same principle as esign-service's public routes: don't confirm
            # or deny anything about a resource to an unauthenticated caller.
            return RedirectResponse(
                _redirect_url(provider=provider, connected=False, message="invalid or expired request")
            )
        except ProviderAuthError as exc:
            return RedirectResponse(
                _redirect_url(provider=provider, connected=False, message=str(exc))
            )
    return RedirectResponse(_redirect_url(provider=provider, connected=True))
