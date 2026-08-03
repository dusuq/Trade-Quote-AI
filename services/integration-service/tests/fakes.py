"""In-memory fakes for repository protocols used in unit tests."""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import IntegrationConnection, SyncLog, WebhookSubscription


class FakeConnectionRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], IntegrationConnection] = {}

    def add(self, conn: IntegrationConnection) -> IntegrationConnection:
        self.items[(conn.tenant_id, conn.id)] = conn
        return conn

    def get(self, tenant_id: UUID, connection_id: UUID) -> IntegrationConnection | None:
        return self.items.get((tenant_id, connection_id))

    def get_by_provider(
        self, tenant_id: UUID, provider: str,
    ) -> IntegrationConnection | None:
        for (tid, _), conn in self.items.items():
            if tid == tenant_id and conn.provider == provider and conn.status in ("active", "pending"):
                return conn
        return None

    def list_for_tenant(self, tenant_id: UUID) -> list[IntegrationConnection]:
        return [conn for (tid, _), conn in self.items.items() if tid == tenant_id]

    def update(self, conn: IntegrationConnection) -> IntegrationConnection:
        self.items[(conn.tenant_id, conn.id)] = conn
        return conn

    def delete(self, tenant_id: UUID, connection_id: UUID) -> bool:
        if (tenant_id, connection_id) in self.items:
            del self.items[(tenant_id, connection_id)]
            return True
        return False


class FakeWebhookRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], WebhookSubscription] = {}

    def add(self, wh: WebhookSubscription) -> WebhookSubscription:
        self.items[(wh.tenant_id, wh.id)] = wh
        return wh

    def get(self, tenant_id: UUID, webhook_id: UUID) -> WebhookSubscription | None:
        return self.items.get((tenant_id, webhook_id))

    def list_for_connection(
        self, tenant_id: UUID, connection_id: UUID,
    ) -> list[WebhookSubscription]:
        return [
            wh
            for (tid, _), wh in self.items.items()
            if tid == tenant_id and wh.connection_id == connection_id
        ]

    def list_active_for_event(
        self, tenant_id: UUID, event_type: str,
    ) -> list[WebhookSubscription]:
        return [
            wh
            for (tid, _), wh in self.items.items()
            if tid == tenant_id and wh.is_active and event_type in wh.event_types
        ]

    def deactivate(self, tenant_id: UUID, webhook_id: UUID) -> bool:
        wh = self.items.get((tenant_id, webhook_id))
        if wh:
            wh.is_active = False
            return True
        return False


class FakeSyncLogRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], SyncLog] = {}

    def add(self, log: SyncLog) -> SyncLog:
        self.items[(log.tenant_id, log.id)] = log
        return log

    def get(self, tenant_id: UUID, sync_log_id: UUID) -> SyncLog | None:
        return self.items.get((tenant_id, sync_log_id))

    def list_for_connection(
        self, tenant_id: UUID, connection_id: UUID, limit: int = 50,
    ) -> list[SyncLog]:
        logs = [
            log
            for (tid, _), log in self.items.items()
            if tid == tenant_id and log.connection_id == connection_id
        ]
        return logs[:limit]

    def update(self, log: SyncLog) -> SyncLog:
        self.items[(log.tenant_id, log.id)] = log
        return log
