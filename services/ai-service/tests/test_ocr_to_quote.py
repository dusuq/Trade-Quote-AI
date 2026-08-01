"""Document -> extraction -> priced line items -> draft quote, one call."""

from __future__ import annotations

import uuid

import pytest

from app.application.ocr_to_quote import OcrToQuoteUseCase
from app.domain.errors import DailySpendCapExceededError, DocumentTooLargeError
from app.domain.models import InputKind
from tests.fakes import (
    FakeDocumentExtractor,
    FakePricebookMatcher,
    FakeQuoteCreator,
    InMemoryUsageRepository,
    make_match,
)

TENANT = uuid.uuid4()
CUSTOMER = uuid.uuid4()
MAX_BYTES = 1_000


def build(*, max_bytes: int = MAX_BYTES, daily_cap_minor: int = 0, spend_today: int = 0):
    extractor = FakeDocumentExtractor()
    matcher = FakePricebookMatcher()
    quote_creator = FakeQuoteCreator()
    usage_repo = InMemoryUsageRepository(spend_today)
    use_case = OcrToQuoteUseCase(
        extractor,
        matcher,
        quote_creator,
        usage_repo,
        max_document_bytes=max_bytes,
        daily_cap_minor=daily_cap_minor,
    )
    return use_case, extractor, matcher, quote_creator, usage_repo


def run(use_case, *, document: bytes = b"x" * 100, mime: str = "image/jpeg"):
    return use_case.execute(
        tenant_id=TENANT,
        user_id=None,
        document_bytes=document,
        mime_type=mime,
        customer_id=CUSTOMER,
    )


def test_creates_a_draft_quote_with_input_kind_ocr() -> None:
    use_case, _extractor, _matcher, quote_creator, usage_repo = build()

    result, events = run(use_case)

    assert result.input_kind == InputKind.OCR
    assert quote_creator.calls[0]["created_via"] == "ocr"
    assert quote_creator.calls[0]["customer_id"] == CUSTOMER
    assert len(usage_repo.recorded) == 1
    assert any(e.event_name == "ai.quote.drafted" for e in events)
    assert any(e.event_name == "ai.usage.recorded" for e in events)


def test_matched_items_use_pricebook_cost_not_extracted_cost() -> None:
    """The extracted `unit_cost_minor` (e.g. from an invoice) never feeds
    pricing directly — quote-service's pricebook stays the single source of
    truth. See the M19 docstring in domain/models.py."""
    use_case, extractor, matcher, quote_creator, _u = build()
    matcher.matches = {
        extractor.extraction.line_items[0].item_name: make_match(unit_cost_minor=9_999)
    }

    run(use_case)

    line_items = quote_creator.calls[0]["line_items"]
    assert line_items[0].unit_cost_minor == 9_999


def test_unmatched_items_are_zero_cost_not_dropped() -> None:
    use_case, *_rest, quote_creator, _u = build()

    run(use_case)

    line_items = quote_creator.calls[-1]["line_items"]
    assert len(line_items) == 1
    assert line_items[0].unit_cost_minor == 0


def test_usage_is_recorded_only_after_the_quote_is_created() -> None:
    use_case, extractor, matcher, _quote_creator, usage_repo = build()

    class ExplodingQuoteCreator:
        def create_quote(self, *args, **kwargs):
            raise RuntimeError("boom")

    use_case = OcrToQuoteUseCase(
        extractor, matcher, ExplodingQuoteCreator(), usage_repo, max_document_bytes=MAX_BYTES
    )

    with pytest.raises(RuntimeError):
        run(use_case)

    assert usage_repo.recorded == []


def test_oversized_document_is_rejected_before_extraction() -> None:
    use_case, extractor, _m, _q, _u = build(max_bytes=10)

    with pytest.raises(DocumentTooLargeError):
        run(use_case, document=b"x" * 5_000)

    assert extractor.calls == []


def test_spend_cap_blocks_before_the_model_call() -> None:
    use_case, extractor, _m, _q, _u = build(daily_cap_minor=10, spend_today=10)

    with pytest.raises(DailySpendCapExceededError):
        run(use_case)

    assert extractor.calls == []
