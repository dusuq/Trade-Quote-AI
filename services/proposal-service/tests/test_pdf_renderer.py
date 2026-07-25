"""Behavioral tests for the PDF renderer — verifies the rendered PDF actually
contains the expected content (via real text extraction), not just that it
didn't crash.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from app.application.pdf_renderer import render_proposal_pdf


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_produces_valid_pdf_bytes(sample_document) -> None:
    pdf_bytes = render_proposal_pdf(sample_document)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_has_a_signature_page(sample_document) -> None:
    pdf_bytes = render_proposal_pdf(sample_document)
    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) >= 2


def test_contains_company_and_customer_names(sample_document) -> None:
    text = _extract_text(render_proposal_pdf(sample_document))
    assert "Bright Sparks Electric" in text
    assert "Jordan Rivera" in text
    assert "742 Evergreen Terrace" in text


def test_contains_line_items_and_formatted_totals(sample_document) -> None:
    text = _extract_text(render_proposal_pdf(sample_document))
    assert "Replace 200A panel" in text
    assert "Install LED recessed lights" in text
    # Money must render as formatted currency, never raw cents.
    assert "$1,511.60" in text  # total
    assert "$1,390.00" in text  # subtotal


def test_contains_warranty_and_terms(sample_document) -> None:
    text = _extract_text(render_proposal_pdf(sample_document))
    assert "2 years" in text
    assert "50% deposit" in text


def test_contains_signature_labels(sample_document) -> None:
    text = _extract_text(render_proposal_pdf(sample_document))
    assert "Customer Signature" in text
    assert "Company Signature" in text


def test_omits_qr_caption_when_no_url_given(sample_document) -> None:
    sample_document.qr_payload_url = None
    text = _extract_text(render_proposal_pdf(sample_document))
    assert "Scan to view" not in text


def test_includes_qr_caption_when_url_given(sample_document) -> None:
    text = _extract_text(render_proposal_pdf(sample_document))
    assert "Scan to view" in text


def test_omits_optional_sections_when_absent(sample_document) -> None:
    sample_document.warranty_text = None
    sample_document.terms_text = None
    text = _extract_text(render_proposal_pdf(sample_document))
    assert "Warranty" not in text
    assert "Terms" not in text
