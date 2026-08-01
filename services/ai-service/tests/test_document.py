"""Pure validation tests for `application/document.py`."""

from __future__ import annotations

import pytest

from app.application.document import normalize_mime_type, validate_document
from app.domain.errors import DocumentTooLargeError, UnsupportedDocumentFormatError


def test_validate_document_accepts_a_supported_format() -> None:
    normalized = validate_document(size_bytes=100, mime_type="image/jpeg", max_bytes=1_000)
    assert normalized == "image/jpeg"


def test_validate_document_normalizes_parameters_and_case() -> None:
    normalized = validate_document(
        size_bytes=100, mime_type="IMAGE/JPEG; charset=binary", max_bytes=1_000
    )
    assert normalized == "image/jpeg"


def test_validate_document_rejects_empty_file() -> None:
    with pytest.raises(UnsupportedDocumentFormatError):
        validate_document(size_bytes=0, mime_type="image/jpeg", max_bytes=1_000)


def test_validate_document_rejects_oversized_upload() -> None:
    with pytest.raises(DocumentTooLargeError):
        validate_document(size_bytes=2_000, mime_type="image/jpeg", max_bytes=1_000)


def test_validate_document_rejects_unsupported_format() -> None:
    with pytest.raises(UnsupportedDocumentFormatError):
        validate_document(size_bytes=100, mime_type="application/pdf", max_bytes=1_000)


def test_normalize_mime_type_strips_params_and_lowercases() -> None:
    assert normalize_mime_type(" IMAGE/PNG ;q=0.9") == "image/png"
