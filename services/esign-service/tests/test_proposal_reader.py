"""Tests for the proposal-service adapter (T204c).

These drive the *real* `ServiceClient` through `httpx.MockTransport` rather
than stubbing it out, so the retry rules, status handling, and header
forwarding that ADR-0003 requires are actually exercised — a hand-rolled stub
would only prove the reader calls something.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.domain.errors import UpstreamServiceError
from app.infrastructure.http import ServiceClient
from app.infrastructure.proposal_reader import HttpProposalReader

TENANT_ID = uuid.uuid4()
PROPOSAL_ID = uuid.uuid4()


def _reader(handler, **kwargs) -> HttpProposalReader:
    client = ServiceClient(
        service_name="proposal-service",
        base_url="http://proposal-service:8005",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        backoff_base_seconds=0.0,  # keep retry tests instant
        **kwargs,
    )
    return HttpProposalReader(client)


def test_returns_the_status_from_a_200() -> None:
    reader = _reader(lambda _req: httpx.Response(200, json={"id": str(PROPOSAL_ID), "status": "sent"}))

    assert reader.get_status(TENANT_ID, PROPOSAL_ID) == "sent"


def test_forwards_the_tenant_header_and_hits_the_right_path() -> None:
    """The tenant header is the whole cross-tenant control — proposal-service
    applies its RLS to whatever we send."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["tenant"] = request.headers["x-tenant-id"]
        return httpx.Response(200, json={"status": "viewed"})

    _reader(handler).get_status(TENANT_ID, PROPOSAL_ID)

    assert seen["path"] == f"/v1/proposals/{PROPOSAL_ID}"
    assert seen["tenant"] == str(TENANT_ID)


def test_404_becomes_none_not_an_error() -> None:
    """Absent (or another tenant's) proposal is an ordinary answer, not a
    failure — the use case turns it into ProposalNotFoundError."""
    reader = _reader(lambda _req: httpx.Response(404, json={"detail": "not found"}))

    assert reader.get_status(TENANT_ID, PROPOSAL_ID) is None


def test_server_error_raises_rather_than_reporting_not_found() -> None:
    reader = _reader(lambda _req: httpx.Response(500, text="boom"), max_attempts=1)

    with pytest.raises(UpstreamServiceError):
        reader.get_status(TENANT_ID, PROPOSAL_ID)


def test_a_200_without_a_status_field_is_an_upstream_error() -> None:
    """The dangerous failure: a malformed 2xx must never be read as 'this
    proposal isn't signable', which would silently block legitimate signing."""
    reader = _reader(lambda _req: httpx.Response(200, json={"id": str(PROPOSAL_ID)}))

    with pytest.raises(UpstreamServiceError):
        reader.get_status(TENANT_ID, PROPOSAL_ID)


def test_a_transient_500_is_retried_because_get_is_idempotent() -> None:
    attempts = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, text="warming up")
        return httpx.Response(200, json={"status": "sent"})

    assert _reader(handler).get_status(TENANT_ID, PROPOSAL_ID) == "sent"
    assert attempts["n"] == 2


def test_connection_failure_surfaces_as_upstream_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(UpstreamServiceError):
        _reader(handler, max_attempts=1).get_status(TENANT_ID, PROPOSAL_ID)
