"""Use cases for proposal create/send/view (T203 / M8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services import render_and_store_proposal_pdf
from app.domain.entities import (
    CompanyBranding,
    CustomerInfo,
    Money,
    ProposalDocument,
    ProposalLineItem,
)
from app.domain.errors import ProposalNotFoundError
from app.domain.events import DomainEvent, proposal_sent, proposal_viewed
from app.domain.proposal import ProposalStatus
from app.domain.storage import PdfStorage
from app.infrastructure.models import ProposalModel, ProposalVersionModel
from app.interface.schemas import ProposalCreate


def generate_proposal_number(session: Session, tenant_id: uuid.UUID) -> str:
    """Sequential proposal number e.g. P-2026-000001 per tenant — same scheme
    as quote-service's generate_quote_number."""
    year = datetime.now(UTC).year
    count = session.scalar(
        select(func.count(ProposalModel.id)).where(ProposalModel.tenant_id == tenant_id)
    ) or 0
    seq = count + 1
    return f"P-{year}-{seq:06d}"


def _to_document(tenant_id: uuid.UUID, proposal_id: uuid.UUID, data: ProposalCreate) -> ProposalDocument:
    return ProposalDocument(
        proposal_id=proposal_id,
        quote_id=data.quote_id,
        tenant_id=tenant_id,
        branding=CompanyBranding(
            company_name=data.branding.company_name,
            logo_path=data.branding.logo_path,
            primary_color=data.branding.primary_color,
            phone=data.branding.phone,
            email=data.branding.email,
            website=data.branding.website,
        ),
        customer=CustomerInfo(
            display_name=data.customer.display_name,
            email=data.customer.email,
            phone=data.customer.phone,
            property_address=data.customer.property_address,
        ),
        line_items=[
            ProposalLineItem(
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=Money(item.unit_price.amount_minor, item.unit_price.currency),
                line_total=Money(item.line_total.amount_minor, item.line_total.currency),
            )
            for item in data.line_items
        ],
        subtotal=Money(data.subtotal.amount_minor, data.subtotal.currency),
        tax=Money(data.tax.amount_minor, data.tax.currency),
        total=Money(data.total.amount_minor, data.total.currency),
        scope_of_work=data.scope_of_work,
        warranty_text=data.warranty_text,
        terms_text=data.terms_text,
        valid_until=data.valid_until,
        qr_payload_url=data.qr_payload_url,
    )


def _document_to_snapshot(doc: ProposalDocument) -> dict:
    return {
        "customer": {
            "display_name": doc.customer.display_name,
            "email": doc.customer.email,
            "phone": doc.customer.phone,
            "property_address": doc.customer.property_address,
        },
        "line_items": [
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit": item.unit,
                "unit_price_minor": item.unit_price.amount_minor,
                "line_total_minor": item.line_total.amount_minor,
            }
            for item in doc.line_items
        ],
        "subtotal_minor": doc.subtotal.amount_minor,
        "tax_minor": doc.tax.amount_minor,
        "total_minor": doc.total.amount_minor,
        "scope_of_work": doc.scope_of_work,
        "warranty_text": doc.warranty_text,
        "terms_text": doc.terms_text,
    }


def create_proposal(
    session: Session,
    storage: PdfStorage,
    tenant_id: uuid.UUID,
    data: ProposalCreate,
) -> tuple[ProposalModel, list[DomainEvent]]:
    proposal_id = uuid.uuid4()
    doc = _to_document(tenant_id, proposal_id, data)

    storage_key, _pdf_bytes, events = render_and_store_proposal_pdf(
        storage, doc, template_id=data.template_id
    )

    proposal = ProposalModel(
        id=proposal_id,
        tenant_id=tenant_id,
        quote_id=data.quote_id,
        template_id=data.template_id,
        number=generate_proposal_number(session, tenant_id),
        status=ProposalStatus.DRAFT,
        current_version=1,
        storage_key=storage_key,
    )
    session.add(proposal)
    session.flush()

    version = ProposalVersionModel(
        tenant_id=tenant_id,
        proposal_id=proposal.id,
        version=1,
        snapshot=_document_to_snapshot(doc),
    )
    session.add(version)
    session.flush()

    return proposal, events


def get_proposal(session: Session, tenant_id: uuid.UUID, proposal_id: uuid.UUID) -> ProposalModel:
    proposal = session.scalar(
        select(ProposalModel).where(
            ProposalModel.id == proposal_id,
            ProposalModel.tenant_id == tenant_id,
        )
    )
    if not proposal:
        raise ProposalNotFoundError(f"Proposal '{proposal_id}' not found.")
    return proposal


def send_proposal(
    session: Session, tenant_id: uuid.UUID, proposal_id: uuid.UUID, *, channel: str
) -> tuple[ProposalModel, DomainEvent]:
    proposal = get_proposal(session, tenant_id, proposal_id)
    proposal.status = ProposalStatus.SENT
    proposal.sent_at = datetime.now(UTC)
    session.flush()
    event = proposal_sent(tenant_id, proposal.id, proposal.quote_id, channel=channel)
    return proposal, event


def mark_viewed_and_fetch_pdf(
    session: Session, storage: PdfStorage, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> tuple[bytes, DomainEvent | None]:
    """Fetch the PDF and, on the first view only, transition SENT -> VIEWED
    and emit proposal.document.viewed. A repeat view returns the PDF again
    with no status change and no second event.

    A DRAFT proposal has never been sent to anyone, so from the public
    /view route's perspective it should look identical to an unknown id —
    raise the same ProposalNotFoundError rather than leaking its existence."""
    proposal = get_proposal(session, tenant_id, proposal_id)
    if proposal.status == ProposalStatus.DRAFT:
        raise ProposalNotFoundError(f"Proposal '{proposal_id}' has not been sent.")
    if proposal.storage_key is None:
        raise ProposalNotFoundError(f"Proposal '{proposal_id}' has no stored PDF.")
    pdf_bytes = storage.read(tenant_id, proposal.storage_key)

    event: DomainEvent | None = None
    if proposal.status != ProposalStatus.VIEWED:
        proposal.status = ProposalStatus.VIEWED
        proposal.viewed_at = datetime.now(UTC)
        session.flush()
        event = proposal_viewed(tenant_id, proposal.id, proposal.viewed_at)

    return pdf_bytes, event


def list_proposals(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID | None = None,
    status: ProposalStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[ProposalModel]:
    stmt = select(ProposalModel).where(ProposalModel.tenant_id == tenant_id)
    if quote_id:
        stmt = stmt.where(ProposalModel.quote_id == quote_id)
    if status:
        stmt = stmt.where(ProposalModel.status == status)
    stmt = stmt.order_by(ProposalModel.created_at.desc()).offset(skip).limit(limit)
    return list(session.scalars(stmt).all())


def list_versions(
    session: Session, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> list[ProposalVersionModel]:
    return list(
        session.scalars(
            select(ProposalVersionModel).where(
                ProposalVersionModel.tenant_id == tenant_id,
                ProposalVersionModel.proposal_id == proposal_id,
            )
        )
    )
