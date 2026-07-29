"""Shared synchronous service-to-service HTTP client.

This is the *only* sanctioned way for this service to call another one
(ADR-0003). It exists because the alternative — an inline `httpx.post` per
call site — is what produced T307b's defects: no timeout discipline, a retry
story that didn't exist, and an exception filter that missed the likeliest
failure.

Every rule ADR-0003 requires is enforced here rather than left to callers:
explicit timeouts, bounded retries on retryable failures only, and every
failure surfaced as `UpstreamServiceError` so no `httpx` type escapes this
layer.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import httpx

from app.domain.errors import UpstreamServiceError

# Methods safe to replay when we don't know whether the server processed the
# request. POST is deliberately absent: retrying a timed-out
# `POST /v1/quotes` could create the quote twice, and a duplicate quote is
# worse than a failed one. Connect errors are still retried for every method,
# because the request provably never left.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE"})


class ServiceClient:
    """One instance per upstream service."""

    def __init__(
        self,
        *,
        service_name: str,
        base_url: str,
        timeout_seconds: float = 5.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        client: httpx.Client | None = None,
    ) -> None:
        self.service_name = service_name
        self.base_url = base_url.rstrip("/")
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def _headers(self, tenant_id: UUID, user_id: UUID | None) -> dict[str, str]:
        """Forward the gateway's identity headers verbatim.

        This service never mints identity — it passes through what the gateway
        already authenticated (conventions §1).
        """
        headers = {"x-tenant-id": str(tenant_id), "content-type": "application/json"}
        if user_id is not None:
            headers["x-user-id"] = str(user_id)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        tenant_id: UUID,
        user_id: UUID | None = None,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Call the upstream and return its decoded JSON body.

        Raises `UpstreamServiceError` on any failure — network, timeout, or a
        non-2xx status.
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
                    headers=self._headers(tenant_id, user_id),
                    json=json,
                    params=params,
                )
            except httpx.TimeoutException as exc:
                # The request may have been processed — only replay it if the
                # method is safe to replay.
                last_error = f"timeout after {self._client.timeout.read}s"
                if not retry_status or attempt == self._max_attempts:
                    raise UpstreamServiceError(self.service_name, last_error) from exc
            except httpx.HTTPError as exc:
                # Connect/transport failure: the upstream never saw it, so
                # replaying is safe regardless of method.
                last_error = f"connection error: {exc}"
                if attempt == self._max_attempts:
                    raise UpstreamServiceError(self.service_name, last_error) from exc
            else:
                if response.is_success:
                    return self._decode(response)

                if 500 <= response.status_code < 600 and retry_status and attempt < self._max_attempts:
                    last_error = f"HTTP {response.status_code}"
                else:
                    # 4xx is never retried: the request was wrong and will be
                    # wrong again next time.
                    raise UpstreamServiceError(
                        self.service_name,
                        f"HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

            time.sleep(self._backoff_base_seconds * (2 ** (attempt - 1)))

        raise UpstreamServiceError(self.service_name, last_error)

    def _decode(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamServiceError(
                self.service_name, "upstream returned a non-JSON body"
            ) from exc

    def close(self) -> None:
        self._client.close()
