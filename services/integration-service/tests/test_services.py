"""Behavioral unit tests for integration service use cases using in-memory fakes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application import services
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
from app.domain.providers import ProviderTokens
from tests.fakes import (
    FakeConnectionRepository,
    FakeInvoiceSyncClient,
    FakeOAuthProvider,
    FakeSyncLogRepository,
    FakeTokenCipher,
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
        cipher = FakeTokenCipher()
        created, _ = services.create_connection(repo, tenant_id=TENANT_A, provider="xero")
        activated, event = services.activate_connection(
            repo,
            cipher,
            tenant_id=TENANT_A,
            connection_id=created.id,
            access_token="plain_access",
            refresh_token="plain_refresh",
            external_account_id="xero_org_123",
        )
        assert activated.status == "active"
        # The stored value is ciphertext, never the plaintext handed in —
        # this is the assertion the T308 audit asked T308b to make possible.
        assert activated.access_token_encrypted == cipher.encrypt("plain_access")
        assert activated.access_token_encrypted != "plain_access"
        assert cipher.decrypt(activated.access_token_encrypted) == "plain_access"
        assert event.event_name == "integration.connection.activated"
        assert event.payload["externalAccountId"] == "xero_org_123"

    def test_raises_when_missing(self) -> None:
        repo = FakeConnectionRepository()
        cipher = FakeTokenCipher()
        with pytest.raises(ConnectionNotFoundError):
            services.activate_connection(
                repo, cipher, tenant_id=TENANT_A, connection_id=uuid.uuid4(), access_token="tok"
            )


class TestRevokeConnection:
    def test_revokes_connection_and_deactivates_webhooks(self) -> None:
        conn_repo = FakeConnectionRepository()
        wh_repo = FakeWebhookRepository()

        conn, _ = services.create_connection(conn_repo, tenant_id=TENANT_A, provider="zapier")
        services.activate_connection(
            conn_repo, FakeTokenCipher(), tenant_id=TENANT_A, connection_id=conn.id, access_token="tok"
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
            conn_repo, FakeTokenCipher(), tenant_id=TENANT_A, connection_id=conn.id, access_token="tok"
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
            conn_repo, FakeTokenCipher(), tenant_id=TENANT_A, connection_id=conn.id, access_token="tok"
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


class TestOAuthFlow:
    """T308b's core deliverable: a real authorization-code exchange for
    QuickBooks/Xero, with the `state` param carrying its own nonce so the
    public callback route can trust it with no tenant header at all."""

    def test_start_oauth_creates_pending_connection_and_authorize_url(self) -> None:
        repo = FakeConnectionRepository()
        provider = FakeOAuthProvider()
        conn, authorize_url = services.start_oauth_connection(
            repo, provider, tenant_id=TENANT_A, provider="quickbooks",
        )
        assert conn.status == "pending"
        assert f"state={TENANT_A}:{conn.id}:" in authorize_url
        # The nonce must actually be persisted — not just embedded in the URL
        # — since the callback (a separate request, no shared memory) reads
        # it back off the connection to authenticate itself.
        assert conn.config_json is not None
        assert "oauth_state" in conn.config_json

    def test_complete_oauth_callback_activates_connection(self) -> None:
        repo = FakeConnectionRepository()
        cipher = FakeTokenCipher()
        provider = FakeOAuthProvider()
        _conn, authorize_url = services.start_oauth_connection(
            repo, provider, tenant_id=TENANT_A, provider="quickbooks",
        )
        state = authorize_url.split("state=")[1]
        # A real QuickBooksProvider fills `external_account_id` from the
        # callback's `realmId` query param (see infrastructure/providers/
        # quickbooks.py); this fake is scripted directly since it doesn't
        # replicate that provider-specific parsing.
        provider.tokens_by_code["auth-code-1"] = ProviderTokens(
            access_token="qb-access-1",
            refresh_token="qb-refresh-1",
            expires_in=3600,
            external_account_id="9999",
        )

        activated, event = services.complete_oauth_callback(
            repo,
            provider,
            cipher,
            state=state,
            code="auth-code-1",
            callback_params={"realmId": "9999", "code": "auth-code-1", "state": state},
        )

        assert activated.status == "active"
        assert activated.external_account_id == "9999"
        assert cipher.decrypt(activated.access_token_encrypted) == "qb-access-1"
        assert cipher.decrypt(activated.refresh_token_encrypted) == "qb-refresh-1"
        assert activated.token_expires_at is not None
        # The nonce is single-use — a replayed callback must not still work.
        assert (activated.config_json or {}).get("oauth_state") is None
        assert event.event_name == "integration.connection.activated"

    def test_complete_oauth_callback_rejects_bad_nonce(self) -> None:
        repo = FakeConnectionRepository()
        provider = FakeOAuthProvider()
        conn, _authorize_url = services.start_oauth_connection(
            repo, provider, tenant_id=TENANT_A, provider="xero",
        )
        forged_state = f"{TENANT_A}:{conn.id}:not-the-real-nonce"
        with pytest.raises(OAuthStateInvalidError):
            services.complete_oauth_callback(
                repo,
                provider,
                FakeTokenCipher(),
                state=forged_state,
                code="whatever",
                callback_params={},
            )

    def test_complete_oauth_callback_rejects_malformed_state(self) -> None:
        repo = FakeConnectionRepository()
        with pytest.raises(OAuthStateInvalidError):
            services.complete_oauth_callback(
                repo,
                FakeOAuthProvider(),
                FakeTokenCipher(),
                state="not-a-valid-state-at-all",
                code="x",
                callback_params={},
            )

    def test_complete_oauth_callback_missing_connection_raises(self) -> None:
        repo = FakeConnectionRepository()
        state = f"{TENANT_A}:{uuid.uuid4()}:some-nonce"
        with pytest.raises(ConnectionNotFoundError):
            services.complete_oauth_callback(
                repo, FakeOAuthProvider(), FakeTokenCipher(), state=state, code="x", callback_params={},
            )


class TestZapierConnect:
    def test_connect_zapier_activates_and_returns_secret_once(self) -> None:
        repo = FakeConnectionRepository()
        cipher = FakeTokenCipher()
        conn, _ = services.create_connection(repo, tenant_id=TENANT_A, provider="zapier")

        activated, secret = services.connect_zapier(
            repo, cipher, tenant_id=TENANT_A, connection_id=conn.id,
        )

        assert activated.status == "active"
        assert cipher.decrypt(activated.access_token_encrypted) == secret

    def test_connect_zapier_rejects_non_zapier_connection(self) -> None:
        repo = FakeConnectionRepository()
        conn, _ = services.create_connection(repo, tenant_id=TENANT_A, provider="quickbooks")
        with pytest.raises(ConnectionInactiveError):
            services.connect_zapier(
                repo, FakeTokenCipher(), tenant_id=TENANT_A, connection_id=conn.id,
            )


class TestPushInvoiceSync:
    def _active_connection(self, *, expires_at: datetime | None = None):
        repo = FakeConnectionRepository()
        cipher = FakeTokenCipher()
        conn, _ = services.create_connection(repo, tenant_id=TENANT_A, provider="quickbooks")
        activated, _ = services.activate_connection(
            repo,
            cipher,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            access_token="access-1",
            refresh_token="refresh-1",
            token_expires_at=expires_at,
            external_account_id="realm-123",
        )
        return repo, cipher, activated

    def test_pushes_invoice_and_records_success(self) -> None:
        repo, cipher, conn = self._active_connection(
            expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        sync_repo = FakeSyncLogRepository()
        oauth_provider = FakeOAuthProvider()
        sync_client = FakeInvoiceSyncClient()
        sync_client.responses.append({"Id": "qb-inv-42"})

        log, event = services.push_invoice_sync(
            repo,
            sync_repo,
            oauth_provider,
            sync_client,
            cipher,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            entity_type="invoice",
            entity_id=uuid.uuid4(),
            payload={"Line": []},
        )

        assert log.status == "success"
        assert log.external_id == "qb-inv-42"
        assert event.event_name == "integration.sync.completed"
        # The provider must have received the plaintext token, never the
        # ciphertext stored on the connection.
        assert sync_client.calls[0]["access_token"] == "access-1"
        assert sync_client.calls[0]["external_account_id"] == "realm-123"

    def test_refreshes_expired_token_before_pushing(self) -> None:
        repo, cipher, conn = self._active_connection(
            expires_at=datetime.now(UTC) - timedelta(minutes=5)
        )
        sync_repo = FakeSyncLogRepository()
        oauth_provider = FakeOAuthProvider()
        oauth_provider.refreshed_tokens = ProviderTokens(
            access_token="refreshed-access",
            refresh_token="refreshed-refresh",
            expires_in=3600,
        )
        sync_client = FakeInvoiceSyncClient()

        log, _event = services.push_invoice_sync(
            repo,
            sync_repo,
            oauth_provider,
            sync_client,
            cipher,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            entity_type="invoice",
            entity_id=None,
            payload={},
        )

        assert log.status == "success"
        assert sync_client.calls[0]["access_token"] == "refreshed-access"
        # The refreshed credential must be persisted, not just used once.
        updated = repo.get(TENANT_A, conn.id)
        assert cipher.decrypt(updated.access_token_encrypted) == "refreshed-access"
        assert cipher.decrypt(updated.refresh_token_encrypted) == "refreshed-refresh"

    def test_refresh_failure_records_failed_sync_without_raising(self) -> None:
        repo, cipher, conn = self._active_connection(
            expires_at=datetime.now(UTC) - timedelta(minutes=5)
        )
        sync_repo = FakeSyncLogRepository()
        oauth_provider = FakeOAuthProvider()
        oauth_provider.raise_on_refresh = ProviderAuthError("refresh token revoked")
        sync_client = FakeInvoiceSyncClient()

        log, _event = services.push_invoice_sync(
            repo,
            sync_repo,
            oauth_provider,
            sync_client,
            cipher,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            entity_type="invoice",
            entity_id=None,
            payload={},
        )

        assert log.status == "failed"
        assert "refresh token revoked" in (log.error_message or "")
        assert sync_client.calls == []  # never reached the push

    def test_push_failure_records_failed_sync_without_raising(self) -> None:
        repo, cipher, conn = self._active_connection(
            expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        sync_repo = FakeSyncLogRepository()
        oauth_provider = FakeOAuthProvider()
        sync_client = FakeInvoiceSyncClient()
        sync_client.raise_on_push = ProviderSyncError("invoice number already exists")

        log, _event = services.push_invoice_sync(
            repo,
            sync_repo,
            oauth_provider,
            sync_client,
            cipher,
            tenant_id=TENANT_A,
            connection_id=conn.id,
            entity_type="invoice",
            entity_id=None,
            payload={},
        )

        assert log.status == "failed"
        assert "invoice number already exists" in (log.error_message or "")

    def test_raises_when_connection_inactive(self) -> None:
        repo = FakeConnectionRepository()
        conn, _ = services.create_connection(repo, tenant_id=TENANT_A, provider="quickbooks")
        with pytest.raises(ConnectionInactiveError):
            services.push_invoice_sync(
                repo,
                FakeSyncLogRepository(),
                FakeOAuthProvider(),
                FakeInvoiceSyncClient(),
                FakeTokenCipher(),
                tenant_id=TENANT_A,
                connection_id=conn.id,
                entity_type="invoice",
                entity_id=None,
                payload={},
            )
