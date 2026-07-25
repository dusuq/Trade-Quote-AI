"""Behavioral tests for the PDF-engine use cases — run against the in-memory
fake storage in tests/fakes.py, no filesystem or DB required.
"""

from __future__ import annotations

import uuid

import pytest

from app.application import services
from app.domain.errors import PdfNotFoundError
from tests.fakes import FakePdfStorage


class TestRenderAndStore:
    def test_stores_pdf_under_tenant_scoped_key(self, sample_document) -> None:
        storage = FakePdfStorage()
        key, pdf_bytes, _events = services.render_and_store_proposal_pdf(storage, sample_document)

        assert key == f"proposals/{sample_document.proposal_id}.pdf"
        assert pdf_bytes.startswith(b"%PDF-")
        # Round-trip: what's stored is exactly what was returned.
        assert storage.read(sample_document.tenant_id, key) == pdf_bytes

    def test_emits_generated_and_rendered_events_matching_registry_shape(self, sample_document) -> None:
        storage = FakePdfStorage()
        _key, pdf_bytes, events = services.render_and_store_proposal_pdf(storage, sample_document)

        assert [e.event_name for e in events] == [
            "proposal.document.generated",
            "proposal.document.pdfRendered",
        ]

        generated, rendered = events
        assert generated.tenant_id == sample_document.tenant_id
        assert generated.payload["proposalId"] == str(sample_document.proposal_id)
        assert generated.payload["quoteId"] == str(sample_document.quote_id)
        assert uuid.UUID(generated.payload["templateId"])  # a valid UUID was generated

        assert rendered.payload["proposalId"] == str(sample_document.proposal_id)
        assert rendered.payload["storageKey"] == f"proposals/{sample_document.proposal_id}.pdf"
        assert rendered.payload["bytes"] == len(pdf_bytes)

    def test_does_not_leak_across_tenants(self, sample_document) -> None:
        storage = FakePdfStorage()
        services.render_and_store_proposal_pdf(storage, sample_document)

        other_tenant = uuid.uuid4()
        key = f"proposals/{sample_document.proposal_id}.pdf"
        with pytest.raises(PdfNotFoundError):
            storage.read(other_tenant, key)


class TestFetchProposalPdf:
    def test_returns_stored_bytes(self, sample_document) -> None:
        storage = FakePdfStorage()
        _key, pdf_bytes, _events = services.render_and_store_proposal_pdf(storage, sample_document)

        fetched = services.fetch_proposal_pdf(storage, sample_document.tenant_id, sample_document.proposal_id)
        assert fetched == pdf_bytes

    def test_raises_when_not_found(self, sample_document) -> None:
        storage = FakePdfStorage()
        with pytest.raises(PdfNotFoundError):
            services.fetch_proposal_pdf(storage, sample_document.tenant_id, uuid.uuid4())
