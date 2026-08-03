"""Shared outbound HTTP client for calling external accounting providers
(QuickBooks Online, Xero).

This is the ADR-0003 pattern (`services/ai-service/app/infrastructure/http.py`
is the reference implementation), ported rather than imported — this repo has
no shared Python runtime package, so each service that calls out over HTTP
keeps its own copy in step (`services/esign-service` does the same for its
proposal-service client).

It differs from the internal service-to-service `ServiceClient` in one way:
internal calls forward the gateway's `x-tenant-id`/`x-user-id` identity
headers, but these are calls to a *third party* (Intuit, Xero) that has never
heard of TradeQuote's tenants — the caller supplies whatever headers that
provider's API needs (Basic auth for token exchange, Bearer for the
accounting API), so headers are a per-request parameter here instead of a
fixed `_headers()` method.

Every rule ADR-0003 requires is still enforced: explicit timeout, bounded
retries on retryable failures only (POST is never replayed after a timeout —
retrying a timed-out invoice push could create it twice), and every failure
raised as `ProviderHttpError` so no raw `httpx` exception reaches a call site.
Call sites (`app/infrastructure/providers/*.py`) catch `ProviderHttpError` and
re-raise as the domain error appropriate to what they were doing
(`ProviderAuthError` for OAuth, `ProviderSyncError` for a data push).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

# Methods safe to replay when we don't know whether the server processed the
# request. POST is deliberately absent: retrying a timed-out
# `POST /v3/company/{id}/invoice` could create the invoice twice, and a
# duplicate invoice is worse than a failed sync. Connect errors are still
# retried for every method, because the request provably never left.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE"})


class ProviderHttpError(Exception):
    """Every failure from `ProviderHttpClient` — network, timeout, or a
    non-2xx status. Never carries the request body/headers in its message,
    so an OAuth token or client secret can't leak into a log line via an
    unguarded `str(exc)`."""

    def __init__(self, provider: str, message: str, *, status_code: int | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider}: {message}")


class ProviderHttpClient:
    """One instance per upstream provider base URL (e.g. QuickBooks's OAuth
    host vs. its accounting-API host are separate instances)."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        client: httpx.Client | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Call the provider and return its decoded JSON body.

        Raises `ProviderHttpError` on any failure — network, timeout, or a
        non-2xx status. `data` sends a form-urlencoded body (the OAuth token
        endpoints require this); `json` sends `application/json` (the
        accounting APIs require this) — never pass both.
        """
        url = f"{self.base_url}{path}"
        method_upper = method.upper()
        retry_status = method_upper in _IDEMPOTENT_METHODS
        last_error: str = "unknown error"

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.request(
                    method_upper,
                    url,
                    headers=headers,
                    json=json,
                    data=data,
                    params=params,
                )
            except httpx.TimeoutException as exc:
                # The request may have been processed — only replay it if the
                # method is safe to replay.
                last_error = f"timeout after {self._client.timeout.read}s"
                if not retry_status or attempt == self._max_attempts:
                    raise ProviderHttpError(self.provider_name, last_error) from exc
            except httpx.HTTPError as exc:
                # Connect/transport failure: the provider never saw it, so
                # replaying is safe regardless of method.
                last_error = f"connection error: {exc}"
                if attempt == self._max_attempts:
                    raise ProviderHttpError(self.provider_name, last_error) from exc
            else:
                if response.is_success:
                    return self._decode(response)

                if (
                    500 <= response.status_code < 600
                    and retry_status
                    and attempt < self._max_attempts
                ):
                    last_error = f"HTTP {response.status_code}"
                else:
                    # 4xx is never retried: the request was wrong (bad code,
                    # expired refresh token, malformed payload) and will be
                    # wrong again next time.
                    raise ProviderHttpError(
                        self.provider_name,
                        f"HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

            time.sleep(self._backoff_base_seconds * (2 ** (attempt - 1)))

        raise ProviderHttpError(self.provider_name, last_error)

    def _decode(self, response: httpx.Response) -> Any:
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderHttpError(
                self.provider_name, "provider returned a non-JSON body"
            ) from exc

    def close(self) -> None:
        self._client.close()
