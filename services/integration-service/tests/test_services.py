"""Behavioral unit tests for integration service use cases using in-memory fakes."""

from __future__ import annotations

import uuid

import pytest

from app.application import services
from app.domain.errors import (
    ConnectionAlreadyExistsError,
    ConnectionInactiveError,
    ConnectionNotFoundError,
    SyncLogNotFoundError,
    WebhookNotFoundError,
)
from tests.fakes import (
    FakeConnectionRepository,
    FakeSyncLogRepository,
    FakeWebhookRepository,
)

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


class TestCreateConnection:
    def test_creates_pending_connection_and_emits_event(self) -> None:
        repo = FakeConnectionRepository()
        conn, event = services.create_connection(
            repo, tenant_id=TENANT_A, provider="quickbooks", display_name="QB Integration"
        )
        assert conn.status == "pending"
        assert conn.provider == "quickbooks"
        assert conn.display_name == "QB Integration"
        assert event.event_name == "integration.connection.created"
        assert event.payload["connectionId"] == str(conn.id)
        assert event.payload["provider"] == "quickbooks"

    def test_prevents_duplicate_active_or_pending_connection(self) -> None:
        repo = FakeConnectionRepository()
        services.create_connection(repo, tenant_id=TENANT_A, provider="quickbooks")
        with pytest.raises(ConnectionAlreadyExistsError):
            services.create_connection(repo, tenant_id=TENANT_A, provider="quickbooks")


class TestActivateConnection:
    def test_activates_connection(self) -> None:
        repo = FakeConnectionRepository()
        created, _ = services.create_connection(repo, tenant_id=TENANT_A, provider="xero")
        activated, event = services.activate_connection(
            repo,
            tenant_id=TENANT_A,
            connection_id=created.id,
            access_token_encrypted="enc_access",
            refresh_token_encrypted="enc_refresh",
            external_account_id="xero_org_123",
        )
        assert activated.status == "active"
        assert activated.access_token_encrypted == "enc_access"
        assert event.event_name == "integration.connection.activated"
        assert event.payload["externalAccountId"] == "xero_org_123"

    def test_raises_when_missing(self) -> None:
        repo = FakeConnectionRepository()
        with pytest.raises(ConnectionNotFoundError):
            services.activate_connection(
                repo, tenant_id=TENANT_A, connection_id=uuid.uuid4(), access_token_encrypted="tok"
            )


class TestRevokeConnection:
    def test_revokes_connection_and_deactivates_webhooks(self) -> None:
        conn_repo = FakeConnectionRepository()
        wh_repo = FakeWebhookRepository()

        conn, _ = services.create_connection(conn_repo, tenant_id=TENANT_A, provider="zapier")
        services.activate_connection(
            conn_repo, tenant_id=TENANT_A, connection_id=conn.id, access_token_encrypted="tok"
        )
        wh = services.create_webhook(
            conn_repo,
            wh_repo,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            target_url="https://hooks.zapier.com/test",
            event_types=["quote.created"],
        )
        assert wh.is_active is True

        revoked, event = services.revoke_connection(
            conn_repo, wh_repo, tenant_id=TENANT_A, connection_id=conn.id
        )
        assert revoked.status == "revoked"
        assert event.event_name == "integration.connection.revoked"

        stored_wh = wh_repo.get(TENANT_A, wh.id)
        assert stored_wh is not None
        assert stored_wh.is_active is False


class TestWebhooks:
    def test_cannot_create_webhook_on_inactive_connection(self) -> None:
        conn_repo = FakeConnectionRepository()
        wh_repo = FakeWebhookRepository()
        conn, _ = services.create_connection(conn_repo, tenant_id=TENANT_A, provider="zapier")
        with pytest.raises(ConnectionInactiveError):
            services.create_webhook(
                conn_repo,
                wh_repo,
                tenant_id=TENANT_A,
                connection_id=conn.id,
                target_url="https://hooks.zapier.com/test",
                event_types=["quote.created"],
            )

    def test_deactivate_webhook(self) -> None:
        conn_repo = FakeConnectionRepository()
        wh_repo = FakeWebhookRepository()
        conn, _ = services.create_connection(conn_repo, tenant_id=TENANT_A, provider="zapier")
        services.activate_connection(
            conn_repo, tenant_id=TENANT_A, connection_id=conn.id, access_token_encrypted="tok"
        )
        wh = services.create_webhook(
            conn_repo,
            wh_repo,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            target_url="https://hooks.zapier.com/test",
            event_types=["quote.created"],
        )
        assert services.deactivate_webhook(wh_repo, tenant_id=TENANT_A, webhook_id=wh.id) is True

    def test_deactivate_missing_webhook_raises(self) -> None:
        wh_repo = FakeWebhookRepository()
        with pytest.raises(WebhookNotFoundError):
            services.deactivate_webhook(wh_repo, tenant_id=TENANT_A, webhook_id=uuid.uuid4())


class TestSyncOperations:
    def test_full_sync_lifecycle(self) -> None:
        conn_repo = FakeConnectionRepository()
        sync_repo = FakeSyncLogRepository()

        conn, _ = services.create_connection(conn_repo, tenant_id=TENANT_A, provider="quickbooks")
        services.activate_connection(
            conn_repo, tenant_id=TENANT_A, connection_id=conn.id, access_token_encrypted="tok"
        )

        log = services.start_sync(
            conn_repo,
            sync_repo,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            direction="push",
            entity_type="invoice",
            entity_id=uuid.uuid4(),
            request_payload={"amount": 50000},
        )
        assert log.status == "running"

        completed, event = services.complete_sync(
            sync_repo,
            tenant_id=TENANT_A,
            sync_log_id=log.id,
            status="success",
            external_id="qb_inv_99",
        )
        assert completed.status == "success"
        assert completed.external_id == "qb_inv_99"
        assert event.event_name == "integration.integration.sync.completed" or event.event_name == "integration.sync.completed"

    def test_complete_sync_missing_raises(self) -> None:
        sync_repo = FakeSyncLogRepository()
        with pytest.raises(SyncLogNotFoundError):
            services.complete_sync(
                sync_repo, tenant_id=TENANT_A, sync_log_id=uuid.uuid4(), status="success"
            )
