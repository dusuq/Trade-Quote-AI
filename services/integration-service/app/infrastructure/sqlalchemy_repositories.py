"""Concrete repository implementations backed by SQLAlchemy/Postgres.
Implements the Protocols in `app.domain.repositories`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import IntegrationConnection, SyncLog, WebhookSubscription
from app.infrastructure.models import (
    IntegrationConnectionModel,
    SyncLogModel,
    WebhookSubscriptionModel,
)


def _to_connection(row: IntegrationConnectionModel) -> IntegrationConnection:
    return IntegrationConnection(
        id=row.id,
        tenant_id=row.tenant_id,
        provider=row.provider,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        external_account_id=row.external_account_id,
        display_name=row.display_name,
        access_token_encrypted=row.access_token_encrypted,
        refresh_token_encrypted=row.refresh_token_encrypted,
        token_expires_at=row.token_expires_at,
        scopes=row.scopes,
        config_json=row.config_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
    )


def _to_webhook(row: WebhookSubscriptionModel) -> WebhookSubscription:
    return WebhookSubscription(
        id=row.id,
        tenant_id=row.tenant_id,
        connection_id=row.connection_id,
        target_url=row.target_url,
        event_types=row.event_types or [],
        secret=row.secret,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _to_sync_log(row: SyncLogModel) -> SyncLog:
    return SyncLog(
        id=row.id,
        tenant_id=row.tenant_id,
        connection_id=row.connection_id,
        direction=row.direction,  # type: ignore[arg-type]
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        status=row.status,  # type: ignore[arg-type]
        external_id=row.external_id,
        error_message=row.error_message,
        request_payload=row.request_payload,
        response_payload=row.response_payload,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


class SqlAlchemyConnectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, conn: IntegrationConnection) -> IntegrationConnection:
        row = IntegrationConnectionModel(
            id=conn.id,
            tenant_id=conn.tenant_id,
            provider=conn.provider,
            status=conn.status,
            external_account_id=conn.external_account_id,
            display_name=conn.display_name,
            access_token_encrypted=conn.access_token_encrypted,
            refresh_token_encrypted=conn.refresh_token_encrypted,
            token_expires_at=conn.token_expires_at,
            scopes=conn.scopes,
            config_json=conn.config_json,
            created_by=conn.created_by,
        )
        self._session.add(row)
        self._session.flush()
        return _to_connection(row)

    def get(self, tenant_id: UUID, connection_id: UUID) -> IntegrationConnection | None:
        row = self._session.get(IntegrationConnectionModel, connection_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_connection(row)

    def get_by_provider(
        self, tenant_id: UUID, provider: str,
    ) -> IntegrationConnection | None:
        stmt = select(IntegrationConnectionModel).where(
            IntegrationConnectionModel.tenant_id == tenant_id,
            IntegrationConnectionModel.provider == provider,
            IntegrationConnectionModel.status.in_(["active", "pending"]),
        )
        row = self._session.scalars(stmt).first()
        return _to_connection(row) if row else None

    def list_for_tenant(self, tenant_id: UUID) -> list[IntegrationConnection]:
        stmt = (
            select(IntegrationConnectionModel)
            .where(IntegrationConnectionModel.tenant_id == tenant_id)
            .order_by(IntegrationConnectionModel.created_at.desc())
        )
        return [_to_connection(r) for r in self._session.scalars(stmt).all()]

    def update(self, conn: IntegrationConnection) -> IntegrationConnection:
        row = self._session.get(IntegrationConnectionModel, conn.id)
        if row is None:
            raise ValueError(f"Connection {conn.id} not found")
        row.status = conn.status
        row.external_account_id = conn.external_account_id
        row.display_name = conn.display_name
        row.access_token_encrypted = conn.access_token_encrypted
        row.refresh_token_encrypted = conn.refresh_token_encrypted
        row.token_expires_at = conn.token_expires_at
        row.scopes = conn.scopes
        row.config_json = conn.config_json
        # The column is non-null; the entity types updated_at optional. It is
        # always set in practice, but coalesce so the type is honest.
        row.updated_at = conn.updated_at or datetime.now(UTC)
        self._session.flush()
        return _to_connection(row)

    def delete(self, tenant_id: UUID, connection_id: UUID) -> bool:
        row = self._session.get(IntegrationConnectionModel, connection_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


class SqlAlchemyWebhookRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, wh: WebhookSubscription) -> WebhookSubscription:
        row = WebhookSubscriptionModel(
            id=wh.id,
            tenant_id=wh.tenant_id,
            connection_id=wh.connection_id,
            target_url=wh.target_url,
            event_types=wh.event_types,
            secret=wh.secret,
            is_active=wh.is_active,
        )
        self._session.add(row)
        self._session.flush()
        return _to_webhook(row)

    def get(self, tenant_id: UUID, webhook_id: UUID) -> WebhookSubscription | None:
        row = self._session.get(WebhookSubscriptionModel, webhook_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_webhook(row)

    def list_for_connection(
        self, tenant_id: UUID, connection_id: UUID,
    ) -> list[WebhookSubscription]:
        stmt = select(WebhookSubscriptionModel).where(
            WebhookSubscriptionModel.tenant_id == tenant_id,
            WebhookSubscriptionModel.connection_id == connection_id,
        )
        return [_to_webhook(r) for r in self._session.scalars(stmt).all()]

    def list_active_for_event(
        self, tenant_id: UUID, event_type: str,
    ) -> list[WebhookSubscription]:
        stmt = select(WebhookSubscriptionModel).where(
            WebhookSubscriptionModel.tenant_id == tenant_id,
            WebhookSubscriptionModel.is_active.is_(True),
        )
        rows = self._session.scalars(stmt).all()
        return [
            _to_webhook(r)
            for r in rows
            if event_type in (r.event_types or [])
        ]

    def deactivate(self, tenant_id: UUID, webhook_id: UUID) -> bool:
        row = self._session.get(WebhookSubscriptionModel, webhook_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        row.is_active = False
        self._session.flush()
        return True


class SqlAlchemySyncLogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, log: SyncLog) -> SyncLog:
        row = SyncLogModel(
            id=log.id,
            tenant_id=log.tenant_id,
            connection_id=log.connection_id,
            direction=log.direction,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            status=log.status,
            external_id=log.external_id,
            error_message=log.error_message,
            request_payload=log.request_payload,
            response_payload=log.response_payload,
            started_at=log.started_at,
            completed_at=log.completed_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_sync_log(row)

    def get(self, tenant_id: UUID, sync_log_id: UUID) -> SyncLog | None:
        row = self._session.get(SyncLogModel, sync_log_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_sync_log(row)

    def list_for_connection(
        self, tenant_id: UUID, connection_id: UUID, limit: int = 50,
    ) -> list[SyncLog]:
        stmt = (
            select(SyncLogModel)
            .where(
                SyncLogModel.tenant_id == tenant_id,
                SyncLogModel.connection_id == connection_id,
            )
            .order_by(SyncLogModel.started_at.desc(), SyncLogModel.id.desc())
            .limit(limit)
        )
        return [_to_sync_log(r) for r in self._session.scalars(stmt).all()]

    def update(self, log: SyncLog) -> SyncLog:
        row = self._session.get(SyncLogModel, log.id)
        if row is None:
            raise ValueError(f"SyncLog {log.id} not found")
        row.status = log.status
        row.external_id = log.external_id
        row.error_message = log.error_message
        row.response_payload = log.response_payload
        row.completed_at = log.completed_at
        self._session.flush()
        return _to_sync_log(row)
