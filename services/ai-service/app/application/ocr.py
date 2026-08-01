"""Shared OCR-pipeline plumbing: document -> extraction -> pricebook match.

Both `DocumentExtractionUseCase` (extract-only "review the document") and
`OcrToQuoteUseCase` (document straight to a draft quote) need the same
extract-then-match step; this module is the one place it happens so the two
flows can't drift apart (same reasoning as `application/vision.py`'s
docstring for the M18 pipeline, and `application/line_items.py`'s for
text/voice).
"""

from __future__ import annotations

from uuid import UUID

from app.domain.errors import DocumentExtractionError
from app.domain.models import (
    AiUsage,
    ExtractedScope,
    ExtractedTask,
    OcrDocumentResult,
    OcrExtractionOutcome,
)
from app.domain.protocols import DocumentExtractor, PricebookMatcher


def document_to_extracted_scope(result: OcrDocumentResult) -> ExtractedScope:
    """Map an OCR extraction onto the same `ExtractedScope` shape the
    text/voice/vision pipelines produce, so `build_line_items` and
    `PricebookMatcher` need no OCR-specific branch.

    A document's own `unit_cost_minor` (when present, e.g. an invoice line)
    is deliberately dropped here — see the M19 module docstring in
    `domain/models.py` for why pricing stays pricebook-authoritative.
    """
    tasks = tuple(
        ExtractedTask(
            description=item.description,
            category=item.category,
            item_name=item.item_name,
            quantity=item.quantity,
            unit=item.unit,
        )
        for item in result.line_items
    )
    return ExtractedScope(
        trade=result.trade,
        summary=result.summary,
        tasks=tasks,
        notes=result.notes,
    )


def extract_and_match(
    extractor: DocumentExtractor,
    matcher: PricebookMatcher,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    document_bytes: bytes,
    mime_type: str,
    document_kind_hint: str | None = None,
) -> tuple[OcrExtractionOutcome, ExtractedScope, AiUsage]:
    """Run extraction then pricebook matching.

    Returns the outcome, the intermediate `ExtractedScope` (what
    `build_line_items` needs when the caller goes on to create a quote), and
    the raw `AiUsage` (what the caller needs to record spend — deliberately
    not folded into the outcome, since usage recording has its own timing
    rules; see `OcrToQuoteUseCase`).
    """
    extraction, usage = extractor.extract_document(document_bytes, mime_type, document_kind_hint)
    if not extraction.line_items:
        raise DocumentExtractionError(
            "no line items could be extracted from that document"
        )

    scope = document_to_extracted_scope(extraction)
    matched_tasks = matcher.match(tenant_id, user_id, list(scope.tasks))

    outcome = OcrExtractionOutcome(
        extraction=extraction,
        matched_tasks=tuple(matched_tasks),
        model_id=usage.model_id,
        tokens_used=usage.tokens_used,
    )
    return outcome, scope, usage
