"""QuickBooks Online — OAuth2 authorization-code exchange/refresh and the
Accounting API v3 invoice endpoint.

Reference: https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0
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


class QuickBooksProvider:
    """Implements `app.domain.providers.OAuthProvider` and `InvoiceSyncClient`.

    `oauth_http`/`api_http` let a test substitute an `httpx.Client` wired to
    `httpx.MockTransport` instead of hitting the real Intuit hosts — each
    `ProviderHttpClient` still owns and closes its own request lifecycle, so
    tests pass two *separate* mock clients (even against the same handler
    function) rather than one shared instance, or the first call's `close()`
    would break the second.
    """

    def __init__(
        self, *, oauth_http: httpx.Client | None = None, api_http: httpx.Client | None = None,
    ) -> None:
        self._api_base = (
            settings.quickbooks_api_base_sandbox
            if settings.quickbooks_environment == "sandbox"
            else settings.quickbooks_api_base_production
        )
        self._oauth_http = oauth_http
        self._api_http = api_http

    def _oauth_client(self) -> ProviderHttpClient:
        return ProviderHttpClient(
            provider_name="quickbooks",
            base_url=settings.quickbooks_oauth_base,
            timeout_seconds=settings.upstream_timeout_seconds,
            max_attempts=settings.upstream_max_attempts,
            client=self._oauth_http,
        )

    def _api_client(self) -> ProviderHttpClient:
        return ProviderHttpClient(
            provider_name="quickbooks",
            base_url=self._api_base,
            timeout_seconds=settings.upstream_timeout_seconds,
            max_attempts=settings.upstream_max_attempts,
            client=self._api_http,
        )

    def _basic_auth_header(self) -> str:
        raw = f"{settings.quickbooks_client_id}:{settings.quickbooks_client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def build_authorize_url(self, *, state: str) -> str:
        params = {
            "client_id": settings.quickbooks_client_id,
            "response_type": "code",
            "scope": settings.quickbooks_scope,
            "redirect_uri": settings.quickbooks_redirect_uri,
            "state": state,
        }
        return f"{settings.quickbooks_authorize_base}?{urlencode(params)}"

    def _parse_token_response(
        self, data: dict[str, Any], *, external_account_id: str | None,
    ) -> ProviderTokens:
        return ProviderTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            external_account_id=external_account_id,
        )

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        """POST to the OAuth token endpoint. Every failure — network,
        timeout, or a non-2xx status — is mapped to `ProviderAuthError` here,
        so no raw `httpx`/`ProviderHttpError` type ever reaches the
        application layer (ADR-0003's "failures mapped to a domain error")."""
        client = self._oauth_client()
        try:
            return client.request(
                "POST",
                "/oauth2/v1/tokens/bearer",
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

    def exchange_code(self, *, code: str, callback_params: dict[str, str]) -> ProviderTokens:
        # QuickBooks includes the company id (realmId) as a query param on
        # the callback redirect itself — there is no separate lookup call
        # like Xero's /connections, so the caller (routes.py) hands it
        # through unchanged via callback_params.
        realm_id = callback_params.get("realmId")
        data = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.quickbooks_redirect_uri,
            }
        )
        return self._parse_token_response(data, external_account_id=realm_id)

    def refresh(self, *, refresh_token: str) -> ProviderTokens:
        data = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
        # QuickBooks rotates the refresh token on every use; the response
        # always carries the new one, which the caller must persist or the
        # next refresh will fail against the now-stale stored value.
        return self._parse_token_response(data, external_account_id=None)

    def push_invoice(
        self, *, access_token: str, external_account_id: str, payload: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._api_client()
        try:
            response = client.request(
                "POST",
                f"/v3/company/{external_account_id}/invoice",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except ProviderHttpError as exc:
            raise ProviderSyncError(str(exc)) from exc
        finally:
            client.close()
        return response.get("Invoice", response) if isinstance(response, dict) else response
