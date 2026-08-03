"""Unit tests for `ProviderHttpClient` — the ADR-0003 rules this service must
obey for outbound calls: explicit timeout, POST never replayed after a
timeout, retries only on retryable failures, every failure surfaced as
`ProviderHttpError`.

Uses `httpx.MockTransport` so these run with no real network access and no
`time.sleep` — `backoff_base_seconds=0` keeps the (still-exercised) retry
loop instant.
"""

from __future__ import annotations

import httpx
import pytest

from app.infrastructure.http import ProviderHttpClient, ProviderHttpError


def _client(handler, **kwargs) -> ProviderHttpClient:
    transport = httpx.MockTransport(handler)
    return ProviderHttpClient(
        provider_name="test-provider",
        base_url="https://provider.test",
        backoff_base_seconds=0,
        client=httpx.Client(transport=transport),
        **kwargs,
    )


def test_get_returns_decoded_json_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert client.request("GET", "/thing") == {"ok": True}


def test_post_is_never_retried_after_a_timeout() -> None:
    """The single most important ADR-0003 rule for this service: replaying a
    timed-out invoice push could create it twice."""
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.TimeoutException("timed out", request=request)

    client = _client(handler, max_attempts=3)
    with pytest.raises(ProviderHttpError):
        client.request("POST", "/invoice", json={})
    assert calls["count"] == 1


def test_get_is_retried_after_a_timeout() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.TimeoutException("timed out", request=request)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, max_attempts=3)
    assert client.request("GET", "/thing") == {"ok": True}
    assert calls["count"] == 3


def test_connect_error_is_retried_regardless_of_method() -> None:
    """The request provably never left, so even POST is safe to replay."""
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, max_attempts=3)
    assert client.request("POST", "/invoice", json={}) == {"ok": True}
    assert calls["count"] == 2


def test_4xx_is_never_retried() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = _client(handler, max_attempts=3)
    with pytest.raises(ProviderHttpError) as exc_info:
        client.request("GET", "/thing")
    assert calls["count"] == 1
    assert exc_info.value.status_code == 400


def test_5xx_is_retried_for_idempotent_methods() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, max_attempts=3)
    assert client.request("GET", "/thing") == {"ok": True}
    assert calls["count"] == 2


def test_5xx_is_not_retried_for_post() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503)

    client = _client(handler, max_attempts=3)
    with pytest.raises(ProviderHttpError):
        client.request("POST", "/invoice", json={})
    assert calls["count"] == 1


def test_error_message_never_includes_request_body() -> None:
    """A failure that echoed the request straight into the exception message
    could leak an access token or client secret into a log line."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    client = _client(handler, max_attempts=1)
    with pytest.raises(ProviderHttpError) as exc_info:
        client.request(
            "POST",
            "/oauth2/v1/tokens/bearer",
            headers={"Authorization": "Basic super-secret-basic-auth"},
            data={"refresh_token": "super-secret-refresh-token"},
        )
    assert "super-secret" not in str(exc_info.value)
