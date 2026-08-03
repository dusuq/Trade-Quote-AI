"""Unit tests for the QuickBooks/Xero OAuth + invoice-push clients.

Every provider call is routed through `httpx.MockTransport` — no real network
access, and no live Intuit/Xero credentials needed to prove the request
shape (auth headers, grant_type, body encoding) and the error-translation
mapping (`ProviderHttpError` → `ProviderAuthError`/`ProviderSyncError`) are
correct.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from app.config import settings
from app.domain.errors import ProviderAuthError, ProviderSyncError
from app.infrastructure.providers.quickbooks import QuickBooksProvider
from app.infrastructure.providers.xero import XeroProvider


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestQuickBooksProvider:
    def test_build_authorize_url_includes_state_and_scope(self) -> None:
        provider = QuickBooksProvider()
        url = provider.build_authorize_url(state="tenant.conn.nonce")
        assert url.startswith(settings.quickbooks_authorize_base)
        assert "state=tenant.conn.nonce" in url
        assert "scope=" in url

    def test_exchange_code_sends_basic_auth_and_form_body(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers["authorization"]
            captured["content_type"] = request.headers["content-type"]
            captured["body"] = request.content.decode()
            return httpx.Response(
                200,
                json={"access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 3600},
            )

        provider = QuickBooksProvider(oauth_http=_mock_client(handler))
        tokens = provider.exchange_code(code="the-code", callback_params={"realmId": "realm-1"})

        assert tokens.access_token == "acc-1"
        assert tokens.refresh_token == "ref-1"
        assert tokens.expires_in == 3600
        assert tokens.external_account_id == "realm-1"
        assert captured["auth"].startswith("Basic ")
        decoded = base64.b64decode(captured["auth"].removeprefix("Basic ")).decode()
        assert decoded == f"{settings.quickbooks_client_id}:{settings.quickbooks_client_secret}"
        assert "application/x-www-form-urlencoded" in captured["content_type"]
        assert "grant_type=authorization_code" in captured["body"]
        assert "code=the-code" in captured["body"]

    def test_exchange_code_failure_raises_provider_auth_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        provider = QuickBooksProvider(oauth_http=_mock_client(handler))
        with pytest.raises(ProviderAuthError):
            provider.exchange_code(code="bad-code", callback_params={})

    def test_refresh_sends_refresh_grant(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content.decode()
            return httpx.Response(
                200,
                json={"access_token": "new-acc", "refresh_token": "new-ref", "expires_in": 3600},
            )

        provider = QuickBooksProvider(oauth_http=_mock_client(handler))
        tokens = provider.refresh(refresh_token="old-ref")

        assert tokens.access_token == "new-acc"
        assert "grant_type=refresh_token" in captured["body"]
        assert "refresh_token=old-ref" in captured["body"]

    def test_push_invoice_sends_bearer_and_realm_in_path(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers["authorization"]
            return httpx.Response(200, json={"Invoice": {"Id": "inv-1"}})

        provider = QuickBooksProvider(api_http=_mock_client(handler))
        result = provider.push_invoice(
            access_token="acc-tok", external_account_id="realm-42", payload={"Line": []},
        )

        assert result == {"Id": "inv-1"}
        assert captured["auth"] == "Bearer acc-tok"
        assert "/v3/company/realm-42/invoice" in captured["url"]

    def test_push_invoice_failure_raises_provider_sync_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"Fault": "duplicate invoice number"})

        provider = QuickBooksProvider(api_http=_mock_client(handler))
        with pytest.raises(ProviderSyncError):
            provider.push_invoice(access_token="acc-tok", external_account_id="realm-42", payload={})


class TestXeroProvider:
    def test_exchange_code_fetches_tenant_id_from_connections(self) -> None:
        def oauth_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 1800},
            )

        def api_handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer acc-1"
            return httpx.Response(200, json=[{"tenantId": "org-abc"}])

        provider = XeroProvider(
            oauth_http=_mock_client(oauth_handler), api_http=_mock_client(api_handler),
        )
        tokens = provider.exchange_code(code="the-code", callback_params={})

        assert tokens.access_token == "acc-1"
        assert tokens.external_account_id == "org-abc"

    def test_exchange_code_with_no_connections_raises_provider_auth_error(self) -> None:
        def oauth_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "acc-1", "expires_in": 1800})

        def api_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        provider = XeroProvider(
            oauth_http=_mock_client(oauth_handler), api_http=_mock_client(api_handler),
        )
        with pytest.raises(ProviderAuthError):
            provider.exchange_code(code="the-code", callback_params={})

    def test_push_invoice_sends_tenant_header(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["tenant_header"] = request.headers["xero-tenant-id"]
            return httpx.Response(200, json={"Invoices": [{"InvoiceID": "inv-9"}]})

        provider = XeroProvider(api_http=_mock_client(handler))
        result = provider.push_invoice(
            access_token="acc-tok", external_account_id="org-abc", payload={"Type": "ACCREC"},
        )

        assert result == {"InvoiceID": "inv-9"}
        assert captured["tenant_header"] == "org-abc"

    def test_push_invoice_failure_raises_provider_sync_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        provider = XeroProvider(api_http=_mock_client(handler))
        with pytest.raises(ProviderSyncError):
            provider.push_invoice(access_token="acc-tok", external_account_id="org-abc", payload={})
