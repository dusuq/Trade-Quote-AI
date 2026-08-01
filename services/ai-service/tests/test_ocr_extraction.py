"""Extract-only flow: document -> line items + matched material list, no quote."""

from __future__ import annotations

import uuid

import pytest

from app.application.ocr_extraction import DocumentExtractionUseCase
from app.domain.errors import (
    DailySpendCapExceededError,
    DocumentExtractionError,
    DocumentTooLargeError,
    UnsupportedDocumentFormatError,
)
from tests.fakes import (
    FakeDocumentExtractor,
    FakePricebookMatcher,
    InMemoryUsageRepository,
    make_document_result,
)

TENANT = uuid.uuid4()
MAX_BYTES = 1_000


def build(*, max_bytes: int = MAX_BYTES, daily_cap_minor: int = 0, spend_today: int = 0):
    extractor = FakeDocumentExtractor()
    matcher = FakePricebookMatcher()
    usage_repo = InMemoryUsageRepository(spend_today)
    use_case = DocumentExtractionUseCase(
        extractor,
        matcher,
        usage_repo,
        max_document_bytes=max_bytes,
        daily_cap_minor=daily_cap_minor,
    )
    return use_case, extractor, matcher, usage_repo


def run(use_case, *, document: bytes = b"x" * 100, mime: str = "image/jpeg"):
    return use_case.execute(
        tenant_id=TENANT, user_id=None, document_bytes=document, mime_type=mime
    )


def test_extracts_and_matches_without_creating_a_quote() -> None:
    use_case, extractor, matcher, usage_repo = build()

    outcome, event = run(use_case)

    assert extractor.calls
    assert matcher.calls
    assert outcome.extraction.line_items
    assert len(usage_repo.recorded) == 1
    assert event.payload["feature"] == "ocr"


def test_no_quote_creator_is_involved() -> None:
    """Extract-only really means extract-only — the use case has no
    reference to a QuoteCreator at all, so there's nothing to accidentally
    call."""
    use_case, *_ = build()
    assert not hasattr(use_case, "_quote_creator")


def test_oversized_document_is_rejected_before_extraction() -> None:
    use_case, extractor, _m, _u = build(max_bytes=10)

    with pytest.raises(DocumentTooLargeError):
        run(use_case, document=b"x" * 5_000)

    assert extractor.calls == []


def test_unsupported_format_is_rejected_before_extraction() -> None:
    use_case, extractor, _m, _u = build()

    with pytest.raises(UnsupportedDocumentFormatError):
        run(use_case, mime="application/pdf")

    assert extractor.calls == []


def test_empty_extraction_raises_before_matching() -> None:
    extractor = FakeDocumentExtractor(make_document_result(line_items=()))
    matcher = FakePricebookMatcher()
    use_case = DocumentExtractionUseCase(
        extractor, matcher, InMemoryUsageRepository(), max_document_bytes=MAX_BYTES
    )

    with pytest.raises(DocumentExtractionError):
        run(use_case)

    assert matcher.calls == []


def test_spend_cap_blocks_before_the_model_call() -> None:
    use_case, extractor, _m, _u = build(daily_cap_minor=10, spend_today=10)

    with pytest.raises(DailySpendCapExceededError):
        run(use_case)

    assert extractor.calls == []
