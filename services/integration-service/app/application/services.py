"""Integration use cases. Depend only on the repository Protocols in
`app.domain.repositories` — fully unit-testable with in-memory fakes,
independent of SQLAlchemy/Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
from app.domain.repositories import (
    ConnectionRepository,
    SyncLogRepository,
    WebhookRepository,
)


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
    *,
    tenant_id: UUID,
    connection_id: UUID,
    access_token_encrypted: str,
    refresh_token_encrypted: str | None = None,
    token_expires_at: datetime | None = None,
    external_account_id: str | None = None,
    scopes: str | None = None,
) -> tuple[IntegrationConnection, DomainEvent]:
    """Activate a connection after OAuth callback succeeds."""
    conn = repo.get(tenant_id, connection_id)
    if conn is None:
        raise ConnectionNotFoundError(str(connection_id))
    conn.status = "active"
    conn.access_token_encrypted = access_token_encrypted
    conn.refresh_token_encrypted = refresh_token_encrypted
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
