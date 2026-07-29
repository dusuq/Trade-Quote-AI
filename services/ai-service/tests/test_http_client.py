"""Shared service client — the retry semantics ADR-0003 requires.

The most important test here is that a POST is *not* replayed after a
timeout: retrying `POST /v1/quotes` blindly could create the quote twice.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.domain.errors import UpstreamServiceError
from app.infrastructure.http import ServiceClient

TENANT = uuid.uuid4()


def build_client(handler, *, max_attempts: int = 3) -> ServiceClient:
    return ServiceClient(
        service_name="test-service",
        base_url="http://upstream",
        max_attempts=max_attempts,
        backoff_base_seconds=0.0,  # keep the suite fast
        client=httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0),
    )


def test_forwards_gateway_identity_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    user_id = uuid.uuid4()
    build_client(handler).request("GET", "/x", tenant_id=TENANT, user_id=user_id)

    assert seen["x-tenant-id"] == str(TENANT)
    assert seen["x-user-id"] == str(user_id)


def test_get_retries_on_5xx_then_succeeds() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    result = build_client(handler).request("GET", "/x", tenant_id=TENANT)

    assert result == {"ok": True}
    assert attempts["n"] == 3


def test_post_is_not_retried_on_5xx() -> None:
    """A POST may have been processed — replaying it could duplicate work."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(500)

    with pytest.raises(UpstreamServiceError):
        build_client(handler).request("POST", "/x", tenant_id=TENANT, json={})

    assert attempts["n"] == 1


def test_post_is_not_retried_after_a_timeout() -> None:
    """The upstream may have created the resource before the clock ran out."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(UpstreamServiceError, match="timeout"):
        build_client(handler).request("POST", "/x", tenant_id=TENANT, json={})

    assert attempts["n"] == 1


def test_connect_errors_are_retried_even_for_post() -> None:
    """A connection that was never established means the request never landed."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(201, json={"id": str(uuid.uuid4())})

    result = build_client(handler).request("POST", "/x", tenant_id=TENANT, json={})

    assert attempts["n"] == 3
    assert "id" in result


def test_4xx_is_never_retried() -> None:
    """The request was wrong; it will be wrong again."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(422, text="bad input")

    with pytest.raises(UpstreamServiceError) as excinfo:
        build_client(handler).request("GET", "/x", tenant_id=TENANT)

    assert attempts["n"] == 1
    assert excinfo.value.status_code == 422


def test_exhausted_retries_raise_a_domain_error_not_an_httpx_error() -> None:
    """ADR-0003 rule 4 — no `httpx` type escapes the infrastructure layer."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(UpstreamServiceError) as excinfo:
        build_client(handler).request("GET", "/x", tenant_id=TENANT)

    assert excinfo.value.service == "test-service"


def test_non_json_body_is_reported_as_an_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(UpstreamServiceError, match="non-JSON"):
        build_client(handler).request("GET", "/x", tenant_id=TENANT)
