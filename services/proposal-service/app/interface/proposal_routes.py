"""HTTP routes for proposals. Every route except /view trusts the gateway's
x-tenant-id — /view is the one deliberately public route in this codebase
(spec D4): a customer opening their proposal link has no session at all.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, Query, Response, status

from app.application import proposal_services
from app.config import settings
from app.domain.errors import PdfNotFoundError, ProposalNotFoundError
from app.domain.proposal import ProposalStatus, TenantResolver
from app.infrastructure.db import PostgresTenantResolver, tenant_session
from app.infrastructure.local_storage import LocalFileStorage
from app.interface.schemas import (
    ProposalCreate,
    ProposalResponse,
    ProposalSendRequest,
    ProposalVersionResponse,
)

router = APIRouter(prefix="/v1/proposals", tags=["proposals"])

_storage = LocalFileStorage(settings.pdf_storage_dir)
_tenant_resolver: TenantResolver = PostgresTenantResolver()


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


@router.post("", response_model=ProposalResponse, status_code=status.HTTP_201_CREATED)
def create_proposal(
    body: ProposalCreate, x_tenant_id: str | None = Header(default=None)
) -> ProposalResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        proposal, _events = proposal_services.create_proposal(session, _storage, tenant_id, body)
        # TODO(outbox): persist _events once a transactional outbox exists
        # (matches the exact TODO already left by T107's render_pdf route).
        return ProposalResponse.model_validate(proposal)


@router.get("", response_model=list[ProposalResponse])
def list_proposals(
    quote_id: uuid.UUID | None = Query(default=None),
    proposal_status: ProposalStatus | None = Query(default=None, alias="status"),
    x_tenant_id: str | None = Header(default=None),
) -> list[ProposalResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        proposals = proposal_services.list_proposals(
            session, tenant_id, quote_id=quote_id, status=proposal_status
        )
        return [ProposalResponse.model_validate(p) for p in proposals]


@router.get("/{proposal_id}", response_model=ProposalResponse)
def get_proposal(
    proposal_id: uuid.UUID, x_tenant_id: str | None = Header(default=None)
) -> ProposalResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            proposal = proposal_services.get_proposal(session, tenant_id, proposal_id)
            return ProposalResponse.model_validate(proposal)
    except ProposalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{proposal_id}/versions", response_model=list[ProposalVersionResponse])
def list_versions(
    proposal_id: uuid.UUID, x_tenant_id: str | None = Header(default=None)
) -> list[ProposalVersionResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        versions = proposal_services.list_versions(session, tenant_id, proposal_id)
        return [ProposalVersionResponse.model_validate(v) for v in versions]


@router.post("/{proposal_id}/send", response_model=ProposalResponse)
def send_proposal(
    proposal_id: uuid.UUID,
    body: ProposalSendRequest | None = None,
    x_tenant_id: str | None = Header(default=None),
) -> ProposalResponse:
    tenant_id = _require_tenant(x_tenant_id)
    channel = body.channel if body else "email"
    try:
        with tenant_session(tenant_id) as session:
            proposal, _event = proposal_services.send_proposal(
                session, tenant_id, proposal_id, channel=channel
            )
            return ProposalResponse.model_validate(proposal)
    except ProposalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{proposal_id}/view")
def view_proposal(proposal_id: uuid.UUID) -> Response:
    """Public — no headers required, no auth of any kind. Resolves its own
    tenant via _tenant_resolver, which bypasses RLS through a narrow
    SECURITY DEFINER function (see infrastructure/db.py)."""
    tenant_id = _tenant_resolver.resolve(proposal_id)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    try:
        with tenant_session(tenant_id) as session:
            pdf_bytes, _event = proposal_services.mark_viewed_and_fetch_pdf(
                session, _storage, tenant_id, proposal_id
            )
    except (ProposalNotFoundError, PdfNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found") from exc
    return Response(content=pdf_bytes, media_type="application/pdf")
