"""Use cases for the PDF engine. Depends only on the PdfStorage Protocol —
fully unit-testable with an in-memory fake, no filesystem or DB required.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.application.pdf_renderer import render_proposal_pdf
from app.domain.entities import ProposalDocument
from app.domain.events import DomainEvent, document_generated, pdf_rendered
from app.domain.storage import PdfStorage


def render_and_store_proposal_pdf(
    storage: PdfStorage,
    doc: ProposalDocument,
    *,
    template_id: UUID | None = None,
) -> tuple[str, bytes, list[DomainEvent]]:
    """Render `doc` to PDF, persist it, and return (storage_key, pdf_bytes, events).

    Callers (e.g. the future Proposal Builder, T203) are responsible for
    persisting the returned events to the transactional outbox.
    """
    pdf_bytes = render_proposal_pdf(doc)
    key = f"proposals/{doc.proposal_id}.pdf"
    storage.save(doc.tenant_id, key, pdf_bytes)

    events = [
        document_generated(doc.tenant_id, doc.proposal_id, doc.quote_id, template_id or uuid4()),
        pdf_rendered(doc.tenant_id, doc.proposal_id, key, len(pdf_bytes)),
    ]
    return key, pdf_bytes, events


def fetch_proposal_pdf(storage: PdfStorage, tenant_id: UUID, proposal_id: UUID) -> bytes:
    """Raises PdfNotFoundError (via the storage backend) if not found."""
    key = f"proposals/{proposal_id}.pdf"
    return storage.read(tenant_id, key)
