"""HTTP routes for the PDF engine.

Trusts the API Gateway's identity headers (x-tenant-id, x-user-id) — the
gateway already verified the JWT (see apps/api-gateway), so this service
never decodes tokens itself.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.application import services
from app.config import settings
from app.domain.entities import (
    CompanyBranding,
    CustomerInfo,
    Money,
    ProposalDocument,
    ProposalLineItem,
)
from app.domain.errors import PdfNotFoundError
from app.infrastructure.local_storage import LocalFileStorage
from app.interface.schemas import RenderProposalRequest, RenderProposalResponse

router = APIRouter(prefix="/v1/proposals", tags=["proposals"])

_storage = LocalFileStorage(settings.pdf_storage_dir)


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _to_domain_document(tenant_id: uuid.UUID, body: RenderProposalRequest) -> ProposalDocument:
    return ProposalDocument(
        proposal_id=uuid.uuid4(),
        quote_id=body.quote_id,
        tenant_id=tenant_id,
        branding=CompanyBranding(
            company_name=body.branding.company_name,
            logo_path=body.branding.logo_path,
            primary_color=body.branding.primary_color,
            phone=body.branding.phone,
            email=body.branding.email,
            website=body.branding.website,
        ),
        customer=CustomerInfo(
            display_name=body.customer.display_name,
            email=body.customer.email,
            phone=body.customer.phone,
            property_address=body.customer.property_address,
        ),
        line_items=[
            ProposalLineItem(
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=Money(item.unit_price.amount_minor, item.unit_price.currency),
                line_total=Money(item.line_total.amount_minor, item.line_total.currency),
            )
            for item in body.line_items
        ],
        subtotal=Money(body.subtotal.amount_minor, body.subtotal.currency),
        tax=Money(body.tax.amount_minor, body.tax.currency),
        total=Money(body.total.amount_minor, body.total.currency),
        scope_of_work=body.scope_of_work,
        warranty_text=body.warranty_text,
        terms_text=body.terms_text,
        valid_until=body.valid_until,
        qr_payload_url=body.qr_payload_url,
    )


@router.post("/pdf", response_model=RenderProposalResponse, status_code=status.HTTP_201_CREATED)
def render_pdf(
    body: RenderProposalRequest,
    x_tenant_id: str | None = Header(default=None),
) -> RenderProposalResponse:
    tenant_id = _require_tenant(x_tenant_id)
    doc = _to_domain_document(tenant_id, body)
    key, pdf_bytes, _events = services.render_and_store_proposal_pdf(_storage, doc)
    # TODO(T203/outbox): persist `_events` (proposal.document.generated +
    # proposal.document.pdfRendered) once the Proposal Builder owns a DB transaction.
    return RenderProposalResponse(
        proposal_id=doc.proposal_id, quote_id=doc.quote_id, storage_key=key, bytes=len(pdf_bytes)
    )


@router.get("/{proposal_id}/pdf")
def get_pdf(proposal_id: uuid.UUID, x_tenant_id: str | None = Header(default=None)) -> Response:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        pdf_bytes = services.fetch_proposal_pdf(_storage, tenant_id, proposal_id)
    except PdfNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal PDF not found") from exc
    return Response(content=pdf_bytes, media_type="application/pdf")
