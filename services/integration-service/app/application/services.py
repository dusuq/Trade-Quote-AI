"""Integration use cases. Depend only on the repository Protocols in
`app.domain.repositories` — fully unit-testable with in-memory fakes,
independent of SQLAlchemy/Postgres.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.domain.entities import (
    IntegrationConnection,
    ProviderKind,
    SyncDirection,
    SyncLog,
    SyncStatus,
    WebhookSubscription,
)
from app.domain.errors import (
    ConnectionAlreadyExistsError,
    ConnectionInactiveError,
    ConnectionNotFoundError,
    OAuthStateInvalidError,
    ProviderAuthError,
    ProviderSyncError,
    SyncLogNotFoundError,
    WebhookNotFoundError,
)
from app.domain.events import (
    DomainEvent,
    connection_activated,
    connection_created,
    connection_revoked,
    sync_completed,
)
from app.domain.providers import InvoiceSyncClient, OAuthProvider, TokenCipher
from app.domain.repositories import (
    ConnectionRepository,
    SyncLogRepository,
    WebhookRepository,
)

# A refresh is attempted proactively once the stored access token is within
# this long of expiring, rather than waiting for the provider to reject it —
# avoids a sync failing on an otherwise-healthy connection purely because of
# clock skew between us and the provider.
_TOKEN_REFRESH_SKEW = timedelta(seconds=60)


def _now() -> datetime:
    return datetime.now(UTC)


def create_connection(
    repo: ConnectionRepository,
    *,
    tenant_id: UUID,
    provider: ProviderKind,
    display_name: str | None = None,
    created_by: UUID | None = None,
) -> tuple[IntegrationConnection, DomainEvent]:
    """Start a new integration connection (pre-OAuth, status=pending)."""
    existing = repo.get_by_provider(tenant_id, provider)
    if existing is not None and existing.status in ("active", "pending"):
        raise ConnectionAlreadyExistsError(
            f"Tenant already has an {existing.status} {provider} connection"
        )
    conn = IntegrationConnection(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider=provider,
        status="pending",
        display_name=display_name or f"{provider.title()} Integration",
        created_at=_now(),
        updated_at=_now(),
        created_by=created_by,
    )
    saved = repo.add(conn)
    event = connection_created(tenant_id, saved.id, saved.provider)
    return saved, event


def activate_connection(
    repo: ConnectionRepository,
    cipher: TokenCipher,
    *,
    tenant_id: UUID,
    connection_id: UUID,
    access_token: str,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
    external_account_id: str | None = None,
    scopes: str | None = None,
) -> tuple[IntegrationConnection, DomainEvent]:
    """Activate a connection with a caller-supplied credential — the manual
    path (a token pasted for testing, or a Zapier secret; see
    `connect_zapier`). The provider OAuth redirect flow goes through
    `complete_oauth_callback` instead, which never lets a plaintext token
    reach an HTTP request body — it goes straight from the provider's
    response into `cipher.encrypt`.

    `access_token`/`refresh_token` are PLAINTEXT in and encrypted here before
    the entity (and therefore the DB row) ever sees them — this is what makes
    `access_token_encrypted` true rather than just a column name.
    """
    conn = repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    conn.status = "active"
    conn.access_token_encrypted = cipher.encrypt(access_token)
    conn.refresh_token_encrypted = cipher.encrypt(refresh_token) if refresh_token else None
    conn.token_expires_at = token_expires_at
    conn.external_account_id = external_account_id
    conn.scopes = scopes
    conn.updated_at = _now()
    saved = repo.update(conn)
    event = connection_activated(tenant_id, saved.id, saved.provider, external_account_id)
    return saved, event


def get_connection(
    repo: ConnectionRepository, *, tenant_id: UUID, connection_id: UUID,
) -> IntegrationConnection:
    conn = repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    return conn


def list_connections(
    repo: ConnectionRepository, *, tenant_id: UUID,
) -> list[IntegrationConnection]:
    return repo.list_for_tenant(tenant_id)


def revoke_connection(
    repo: ConnectionRepository,
    webhook_repo: WebhookRepository,
    *,
    tenant_id: UUID,
    connection_id: UUID,
) -> tuple[IntegrationConnection, DomainEvent]:
    """Revoke (soft-delete) a connection and deactivate all its webhooks."""
    conn = repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    conn.status = "revoked"
    conn.access_token_encrypted = None
    conn.refresh_token_encrypted = None
    conn.updated_at = _now()
    saved = repo.update(conn)
    # Deactivate all webhooks for this connection
    webhooks = webhook_repo.list_for_connection(tenant_id, connection_id)
    for wh in webhooks:
        if wh.is_active:
            webhook_repo.deactivate(tenant_id, wh.id)
    event = connection_revoked(tenant_id, saved.id, saved.provider)
    return saved, event


# ── OAuth (QuickBooks / Xero) ────────────────────────────────────────────


def start_oauth_connection(
    repo: ConnectionRepository,
    oauth_provider: OAuthProvider,
    *,
    tenant_id: UUID,
    provider: ProviderKind,
    display_name: str | None = None,
    created_by: UUID | None = None,
) -> tuple[IntegrationConnection, str]:
    """Create a pending connection and return the provider's authorize URL.

    Zapier has no OAuth flow (it's API-key/webhook based — see
    `connect_zapier`); callers must not reach this use case for it.
    """
    conn, _event = create_connection(
        repo,
        tenant_id=tenant_id,
        provider=provider,
        display_name=display_name,
        created_by=created_by,
    )
    # A per-attempt random nonce, not the connection id itself, is what the
    # callback actually verifies — see `complete_oauth_callback`. Without it,
    # anyone who can guess or observe a connection id (they are returned from
    # `POST /connections`, not secret) could replay a stale/foreign `code`
    # against it.
    nonce = secrets.token_urlsafe(32)
    conn.config_json = {**(conn.config_json or {}), "oauth_state": nonce}
    saved = repo.update(conn)
    state = f"{tenant_id}:{saved.id}:{nonce}"
    return saved, oauth_provider.build_authorize_url(state=state)


def complete_oauth_callback(
    repo: ConnectionRepository,
    oauth_provider: OAuthProvider,
    cipher: TokenCipher,
    *,
    state: str,
    code: str,
    callback_params: dict[str, str],
) -> tuple[IntegrationConnection, DomainEvent]:
    """Finish the OAuth dance after the provider redirects the browser back.

    This runs behind a PUBLIC route (see `app/interface/routes.py`'s
    `public_router`) — the browser lands here straight from the provider with
    no TradeQuote session, so there is no `x-tenant-id` header to trust. The
    tenant and connection ids embedded in `state` are just routing — the
    nonce is the actual credential, checked with a constant-time comparison
    against the one stashed on the connection by `start_oauth_connection`.
    """
    try:
        tenant_id_str, connection_id_str, nonce = state.split(":", 2)
        tenant_id = UUID(tenant_id_str)
        connection_id = UUID(connection_id_str)
    except (ValueError, AttributeError) as exc:
        raise OAuthStateInvalidError("malformed OAuth state") from exc

    conn = repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    expected_nonce = (conn.config_json or {}).get("oauth_state")
    if not expected_nonce or not secrets.compare_digest(expected_nonce, nonce):
        raise OAuthStateInvalidError("OAuth state does not match the connection it targets")

    tokens = oauth_provider.exchange_code(code=code, callback_params=callback_params)

    conn.status = "active"
    conn.access_token_encrypted = cipher.encrypt(tokens.access_token)
    conn.refresh_token_encrypted = (
        cipher.encrypt(tokens.refresh_token) if tokens.refresh_token else None
    )
    conn.token_expires_at = (
        _now() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None
    )
    conn.external_account_id = tokens.external_account_id
    conn.config_json = {k: v for k, v in (conn.config_json or {}).items() if k != "oauth_state"}
    conn.updated_at = _now()
    saved = repo.update(conn)
    event = connection_activated(tenant_id, saved.id, saved.provider, saved.external_account_id)
    return saved, event


def connect_zapier(
    repo: ConnectionRepository,
    cipher: TokenCipher,
    *,
    tenant_id: UUID,
    connection_id: UUID,
) -> tuple[IntegrationConnection, str]:
    """Activate a Zapier connection by minting a signing secret server-side.

    Zapier is API-key/webhook based, not OAuth — there is no authorization
    server to redirect to. The secret this generates is what the tenant
    pastes into their Zap's "Webhooks by Zapier" auth step; TradeQuote uses
    the same secret to sign the payloads it sends to `webhook_subscription`
    target URLs. Returned in plaintext exactly once — like an API key, it is
    not retrievable again after this call, only rotatable (call this again).
    """
    conn = repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    if conn.provider != "zapier":
        raise ConnectionInactiveError(
            f"connection {connection_id} is a {conn.provider} connection, not zapier"
        )
    secret = secrets.token_urlsafe(32)
    conn.status = "active"
    conn.access_token_encrypted = cipher.encrypt(secret)
    conn.refresh_token_encrypted = None
    conn.updated_at = _now()
    saved = repo.update(conn)
    return saved, secret


def push_invoice_sync(
    conn_repo: ConnectionRepository,
    sync_repo: SyncLogRepository,
    oauth_provider: OAuthProvider,
    sync_client: InvoiceSyncClient,
    cipher: TokenCipher,
    *,
    tenant_id: UUID,
    connection_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    payload: dict,
) -> tuple[SyncLog, DomainEvent]:
    """Push one quote/invoice to the connected QuickBooks/Xero account and
    record the result as a `SyncLog` — the "actual sync" T308b was scoped to
    deliver, as opposed to T308's connection-state-only scaffold.

    Refreshes the stored access token first if it is expired or expiring
    within `_TOKEN_REFRESH_SKEW`, persisting the refreshed credential before
    attempting the push so a successful refresh is never thrown away by a
    push that then fails for an unrelated reason.
    """
    conn = conn_repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    if conn.status != "active":
        raise ConnectionInactiveError(f"Connection {connection_id} is {conn.status}")
    if not conn.access_token_encrypted or not conn.external_account_id:
        raise ConnectionInactiveError(
            f"Connection {connection_id} has no stored provider credentials"
        )
    # Never reassigned below (unlike the token fields, which the refresh
    # branch rewrites) — safe to narrow once, here, past the `is None` guard.
    external_account_id: str = conn.external_account_id

    log = start_sync(
        conn_repo,
        sync_repo,
        tenant_id=tenant_id,
        connection_id=connection_id,
        direction="push",
        entity_type=entity_type,
        entity_id=entity_id,
        request_payload=payload,
    )

    needs_refresh = conn.token_expires_at is not None and conn.token_expires_at <= (
        _now() + _TOKEN_REFRESH_SKEW
    )
    if needs_refresh:
        if not conn.refresh_token_encrypted:
            return complete_sync(
                sync_repo,
                tenant_id=tenant_id,
                sync_log_id=log.id,
                status="failed",
                error_message="access token expired and no refresh token is stored",
            )
        try:
            refreshed = oauth_provider.refresh(
                refresh_token=cipher.decrypt(conn.refresh_token_encrypted)
            )
        except ProviderAuthError as exc:
            return complete_sync(
                sync_repo,
                tenant_id=tenant_id,
                sync_log_id=log.id,
                status="failed",
                error_message=f"token refresh failed: {exc}",
            )
        conn.access_token_encrypted = cipher.encrypt(refreshed.access_token)
        if refreshed.refresh_token:
            conn.refresh_token_encrypted = cipher.encrypt(refreshed.refresh_token)
        conn.token_expires_at = (
            _now() + timedelta(seconds=refreshed.expires_in) if refreshed.expires_in else None
        )
        conn.updated_at = _now()
        conn = conn_repo.update(conn)

    access_token = cipher.decrypt(conn.access_token_encrypted)  # type: ignore[arg-type]
    try:
        response = sync_client.push_invoice(
            access_token=access_token,
            external_account_id=external_account_id,
            payload=payload,
        )
    except ProviderSyncError as exc:
        return complete_sync(
            sync_repo,
            tenant_id=tenant_id,
            sync_log_id=log.id,
            status="failed",
            error_message=str(exc),
        )

    external_id = response.get("Id") or response.get("InvoiceID") if isinstance(response, dict) else None
    return complete_sync(
        sync_repo,
        tenant_id=tenant_id,
        sync_log_id=log.id,
        status="success",
        external_id=str(external_id) if external_id else None,
        response_payload=response if isinstance(response, dict) else None,
    )


# ── Webhook management ──────────────────────────────────────────────────


def create_webhook(
    conn_repo: ConnectionRepository,
    wh_repo: WebhookRepository,
    *,
    tenant_id: UUID,
    connection_id: UUID,
    target_url: str,
    event_types: list[str],
    secret: str | None = None,
) -> WebhookSubscription:
    """Register a webhook subscription for a connection."""
    conn = conn_repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    if conn.status != "active":
        raise ConnectionInactiveError(f"Connection {connection_id} is {conn.status}")
    wh = WebhookSubscription(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=connection_id,
        target_url=target_url,
        event_types=event_types,
        secret=secret,
        is_active=True,
        created_at=_now(),
    )
    return wh_repo.add(wh)


def list_webhooks(
    wh_repo: WebhookRepository, *, tenant_id: UUID, connection_id: UUID,
) -> list[WebhookSubscription]:
    return wh_repo.list_for_connection(tenant_id, connection_id)


def deactivate_webhook(
    wh_repo: WebhookRepository, *, tenant_id: UUID, webhook_id: UUID,
) -> bool:
    wh = wh_repo.get(tenant_id, webhook_id)
    if wh is None:
        raise WebhookNotFoundError(str(webhook_id))
    return wh_repo.deactivate(tenant_id, webhook_id)


# ── Sync operations ─────────────────────────────────────────────────────


def start_sync(
    conn_repo: ConnectionRepository,
    sync_repo: SyncLogRepository,
    *,
    tenant_id: UUID,
    connection_id: UUID,
    direction: SyncDirection,
    entity_type: str,
    entity_id: UUID | None = None,
    request_payload: dict | None = None,
) -> SyncLog:
    """Begin a sync operation, returning the log entry."""
    conn = conn_repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    if conn.status != "active":
        raise ConnectionInactiveError(f"Connection {connection_id} is {conn.status}")
    log = SyncLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=connection_id,
        direction=direction,
        entity_type=entity_type,
        entity_id=entity_id,
        status="running",
        request_payload=request_payload,
        started_at=_now(),
    )
    return sync_repo.add(log)


def complete_sync(
    sync_repo: SyncLogRepository,
    *,
    tenant_id: UUID,
    sync_log_id: UUID,
    status: SyncStatus,
    external_id: str | None = None,
    error_message: str | None = None,
    response_payload: dict | None = None,
) -> tuple[SyncLog, DomainEvent]:
    """Mark a sync log as completed (success or failed)."""
    log = sync_repo.get(tenant_id, sync_log_id)
    if log is None:
        raise SyncLogNotFoundError(str(sync_log_id))
    log.status = status
    log.external_id = external_id
    log.error_message = error_message
    log.response_payload = response_payload
    log.completed_at = _now()
    saved = sync_repo.update(log)
    event = sync_completed(
        tenant_id, saved.connection_id, saved.id, saved.entity_type, saved.direction, status,
    )
    return saved, event


def list_sync_logs(
    sync_repo: SyncLogRepository,
    *,
    tenant_id: UUID,
    connection_id: UUID,
    limit: int = 50,
) -> list[SyncLog]:
    return sync_repo.list_for_connection(tenant_id, connection_id, limit=limit)
