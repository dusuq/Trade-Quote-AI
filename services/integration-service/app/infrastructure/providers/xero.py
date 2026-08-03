"""Xero — OAuth2 authorization-code exchange/refresh and the Accounting API
Invoices endpoint.

Xero's callback carries no organisation identifier the way QuickBooks's
`realmId` does — a token can be authorized for multiple orgs at once — so
after exchanging the code this client makes one extra call to
`GET /connections` to discover the org (`tenantId`) the user actually
connected, and reports it back as `ProviderTokens.external_account_id`
(the same field QuickBooks fills from its callback query param).

Reference: https://developer.xero.com/documentation/guides/oauth2/auth-flow/
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.domain.errors import ProviderAuthError, ProviderSyncError
from app.domain.providers import ProviderTokens
from app.infrastructure.http import ProviderHttpClient, ProviderHttpError


class XeroProvider:
    """Implements `app.domain.providers.OAuthProvider` and `InvoiceSyncClient`.

    See `QuickBooksProvider` for why `oauth_http`/`api_http` are separate
    injection points rather than one shared client.
    """

    def __init__(
        self, *, oauth_http: httpx.Client | None = None, api_http: httpx.Client | None = None,
    ) -> None:
        self._oauth_http = oauth_http
        self._api_http = api_http

    def _oauth_client(self) -> ProviderHttpClient:
        return ProviderHttpClient(
            provider_name="xero",
            base_url=settings.xero_oauth_base,
            timeout_seconds=settings.upstream_timeout_seconds,
            max_attempts=settings.upstream_max_attempts,
            client=self._oauth_http,
        )

    def _api_client(self) -> ProviderHttpClient:
        return ProviderHttpClient(
            provider_name="xero",
            base_url=settings.xero_api_base,
            timeout_seconds=settings.upstream_timeout_seconds,
            max_attempts=settings.upstream_max_attempts,
            client=self._api_http,
        )

    def _basic_auth_header(self) -> str:
        raw = f"{settings.xero_client_id}:{settings.xero_client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def build_authorize_url(self, *, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.xero_client_id,
            "redirect_uri": settings.xero_redirect_uri,
            "scope": settings.xero_scope,
            "state": state,
        }
        return f"{settings.xero_authorize_base}?{urlencode(params)}"

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        """POST to the OAuth token endpoint. Every failure is mapped to
        `ProviderAuthError` here — see quickbooks.py's `_token_request` for
        why that mapping lives at this layer rather than the application."""
        client = self._oauth_client()
        try:
            return client.request(
                "POST",
                "/connect/token",
                headers={
                    "Authorization": self._basic_auth_header(),
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=form,
            )
        except ProviderHttpError as exc:
            raise ProviderAuthError(str(exc)) from exc
        finally:
            client.close()

    def _fetch_tenant_id(self, access_token: str) -> str | None:
        client = self._api_client()
        try:
            connections = client.request(
                "GET",
                "/connections",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        except ProviderHttpError as exc:
            raise ProviderAuthError(str(exc)) from exc
        finally:
            client.close()
        if isinstance(connections, list) and connections:
            return connections[0].get("tenantId")
        return None

    def exchange_code(self, *, code: str, callback_params: dict[str, str]) -> ProviderTokens:
        data = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.xero_redirect_uri,
            }
        )
        tenant_id = self._fetch_tenant_id(data["access_token"])
        if tenant_id is None:
            raise ProviderAuthError(
                "xero authorized with no connected organisation — grant access to one in the consent screen"
            )
        return ProviderTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            external_account_id=tenant_id,
        )

    def refresh(self, *, refresh_token: str) -> ProviderTokens:
        data = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
        # Xero rotates the refresh token on every use, same as QuickBooks —
        # the caller must persist the new one or the next refresh 400s.
        return ProviderTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            external_account_id=None,
        )

    def push_invoice(
        self, *, access_token: str, external_account_id: str, payload: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._api_client()
        try:
            response = client.request(
                "POST",
                "/api.xro/2.0/Invoices",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Xero-tenant-id": external_account_id,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except ProviderHttpError as exc:
            raise ProviderSyncError(str(exc)) from exc
        finally:
            client.close()
        invoices = response.get("Invoices") if isinstance(response, dict) else None
        return invoices[0] if invoices else response
