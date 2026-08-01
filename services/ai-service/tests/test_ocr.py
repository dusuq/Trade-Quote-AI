"""Shared plumbing: document -> extraction -> pricebook match."""

from __future__ import annotations

import uuid

import pytest

from app.application.ocr import document_to_extracted_scope, extract_and_match
from app.domain.errors import DocumentExtractionError
from app.domain.models import DocumentKind
from tests.fakes import (
    FakeDocumentExtractor,
    FakePricebookMatcher,
    make_document_result,
    make_ocr_line_item,
)

TENANT = uuid.uuid4()


def test_document_to_extracted_scope_maps_line_items_to_tasks() -> None:
    result = make_document_result(
        line_items=(make_ocr_line_item("Copper pipe"), make_ocr_line_item("Coupling"))
    )

    scope = document_to_extracted_scope(result)

    assert scope.trade == result.trade
    assert scope.summary == result.summary
    assert [t.item_name for t in scope.tasks] == ["Copper pipe", "Coupling"]


def test_extract_and_match_returns_outcome_scope_and_usage() -> None:
    extractor = FakeDocumentExtractor()
    matcher = FakePricebookMatcher()

    outcome, scope, usage = extract_and_match(
        extractor,
        matcher,
        tenant_id=TENANT,
        user_id=None,
        document_bytes=b"x" * 100,
        mime_type="image/jpeg",
    )

    assert outcome.extraction == extractor.extraction
    assert len(scope.tasks) == len(extractor.extraction.line_items)
    assert usage.feature.value == "ocr"
    assert matcher.calls


def test_extract_and_match_raises_when_no_line_items_found() -> None:
    extractor = FakeDocumentExtractor(
        make_document_result(line_items=(), document_kind=DocumentKind.BLUEPRINT)
    )
    matcher = FakePricebookMatcher()

    with pytest.raises(DocumentExtractionError):
        extract_and_match(
            extractor,
            matcher,
            tenant_id=TENANT,
            user_id=None,
            document_bytes=b"x" * 100,
            mime_type="image/jpeg",
        )

    assert matcher.calls == []
