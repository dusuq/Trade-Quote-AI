"""In-memory fakes for repository/provider protocols used in unit tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain.entities import IntegrationConnection, SyncLog, WebhookSubscription
from app.domain.providers import ProviderTokens


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


class FakeTokenCipher:
    """Reversible, NOT secure — a real `cryptography.fernet` round trip is
    covered by `tests/test_crypto.py`. This fake just needs to prove
    `services.py` calls `encrypt`/`decrypt` at the right points, so a visible
    prefix (rather than a no-op passthrough) makes it obvious in an assertion
    if a plaintext token ever reached storage unencrypted."""

    PREFIX = "fake-encrypted:"

    def encrypt(self, plaintext: str) -> str:
        return f"{self.PREFIX}{plaintext}"

    def decrypt(self, ciphertext: str) -> str:
        assert ciphertext.startswith(self.PREFIX), f"not encrypted by this fake: {ciphertext!r}"
        return ciphertext[len(self.PREFIX):]


class FakeOAuthProvider:
    """Scripted OAuth provider — no network calls. Configure `tokens_by_code`
    /`refreshed_tokens` per test; `build_authorize_url` just echoes `state`
    back so a test can assert it was minted and threaded through correctly."""

    def __init__(self) -> None:
        self.tokens_by_code: dict[str, ProviderTokens] = {}
        self.refreshed_tokens: ProviderTokens | None = None
        self.raise_on_exchange: Exception | None = None
        self.raise_on_refresh: Exception | None = None
        self.last_callback_params: dict[str, str] | None = None

    def build_authorize_url(self, *, state: str) -> str:
        return f"https://fake-provider.test/authorize?state={state}"

    def exchange_code(self, *, code: str, callback_params: dict[str, str]) -> ProviderTokens:
        self.last_callback_params = callback_params
        if self.raise_on_exchange:
            raise self.raise_on_exchange
        return self.tokens_by_code[code]

    def refresh(self, *, refresh_token: str) -> ProviderTokens:
        if self.raise_on_refresh:
            raise self.raise_on_refresh
        assert self.refreshed_tokens is not None, "test must set refreshed_tokens"
        return self.refreshed_tokens


class FakeInvoiceSyncClient:
    """Scripted invoice push — no network calls."""

    def __init__(self) -> None:
        self.responses: list[dict[str, Any]] = []
        self.raise_on_push: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    def push_invoice(
        self, *, access_token: str, external_account_id: str, payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "access_token": access_token,
                "external_account_id": external_account_id,
                "payload": payload,
            }
        )
        if self.raise_on_push:
            raise self.raise_on_push
        return self.responses.pop(0) if self.responses else {"Id": "ext-1"}
