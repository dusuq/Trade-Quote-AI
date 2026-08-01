"""Reads proposal state from proposal-service over HTTP.

ADR-0003 permits this call because it is *part of fulfilling the request*: if
it fails, creating the signature request is not meaningfully complete — we'd
be binding a legal audit trail to a document we never confirmed exists.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain.errors import UpstreamServiceError
from app.infrastructure.http import ServiceClient


class HttpProposalReader:
    """`ProposalReader` backed by `GET /v1/proposals/{id}`."""

    def __init__(self, client: ServiceClient) -> None:
        self._client = client

    def get_status(self, tenant_id: UUID, proposal_id: UUID) -> str | None:
        try:
            body: Any = self._client.request(
                "GET", f"/v1/proposals/{proposal_id}", tenant_id=tenant_id
            )
        except UpstreamServiceError as exc:
            # proposal-service returns 404 both for "no such proposal" and for
            # one belonging to another tenant (its own RLS scopes the read to
            # the tenant header we forwarded). Collapsing both to None is
            # correct and keeps us from distinguishing the two.
            if exc.status_code == 404:
                return None
            raise

        status = body.get("status") if isinstance(body, dict) else None
        if not isinstance(status, str) or not status:
            # A 2xx whose shape we don't recognise is an upstream failure, not
            # an unsignable proposal — never silently treat it as a rejection.
            raise UpstreamServiceError(
                self._client.service_name,
                "proposal response had no usable 'status' field",
            )
        return status
