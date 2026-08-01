"""Use case: document -> structured extraction -> priced line items -> draft
quote.

Mirrors `vision_to_quote.py`'s pipeline shape (cap check -> extract -> match
-> build line items -> create quote -> record usage) with the extraction
step replaced by `application.ocr.extract_and_match`. Applies to all three
document kinds: an invoice's material lines, a blueprint's takeoff, or a
handwritten job list all become billable scope the same way.
"""

from __future__ import annotations

from uuid import UUID

from app.application.document import validate_document
from app.application.line_items import DEFAULT_MARKUP_BPS, build_line_items
from app.application.ocr import extract_and_match
from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, quote_drafted, usage_recorded
from app.domain.models import InputKind, QuoteAssistantResult
from app.domain.protocols import (
    AiUsageRepository,
    DocumentExtractor,
    PricebookMatcher,
    QuoteCreator,
)

_MAX_TITLE_LENGTH = 255
_CREATED_VIA = "ocr"


class OcrToQuoteUseCase:
    def __init__(
        self,
        extractor: DocumentExtractor,
        matcher: PricebookMatcher,
        quote_creator: QuoteCreator,
        usage_repo: AiUsageRepository,
        *,
        max_document_bytes: int,
        daily_cap_minor: int = 0,
    ) -> None:
        self._extractor = extractor
        self._matcher = matcher
        self._quote_creator = quote_creator
        self._usage_repo = usage_repo
        self._max_document_bytes = max_document_bytes
        self._daily_cap_minor = daily_cap_minor

    def _check_spend_cap(self, tenant_id: UUID) -> None:
        if self._daily_cap_minor <= 0:
            return
        spent = self._usage_repo.spend_today_minor(tenant_id)
        if spent >= self._daily_cap_minor:
            raise DailySpendCapExceededError(
                f"daily AI spend cap reached ({spent} of {self._daily_cap_minor} minor units)"
            )

    def execute(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        document_bytes: bytes,
        mime_type: str,
        customer_id: UUID,
        property_id: UUID | None = None,
        title: str | None = None,
        document_kind_hint: str | None = None,
        tax_rate_bps: int = 0,
        default_markup_bps: int = DEFAULT_MARKUP_BPS,
    ) -> tuple[QuoteAssistantResult, list[DomainEvent]]:
        self._check_spend_cap(tenant_id)

        normalized_mime = validate_document(
            size_bytes=len(document_bytes),
            mime_type=mime_type,
            max_bytes=self._max_document_bytes,
        )

        outcome, scope, usage = extract_and_match(
            self._extractor,
            self._matcher,
            tenant_id=tenant_id,
            user_id=user_id,
            document_bytes=document_bytes,
            mime_type=normalized_mime,
            document_kind_hint=document_kind_hint,
        )

        line_items = build_line_items(
            list(outcome.matched_tasks), default_markup_bps=default_markup_bps
        )

        quote_id = self._quote_creator.create_quote(
            tenant_id,
            user_id,
            customer_id=customer_id,
            property_id=property_id,
            title=(title or scope.summary)[:_MAX_TITLE_LENGTH],
            created_via=_CREATED_VIA,
            tax_rate_bps=tax_rate_bps,
            line_items=line_items,
        )

        # Recorded only after the quote exists — same reasoning as
        # text_to_quote.py: billing a run that produced nothing would be
        # backwards.
        self._usage_repo.record(tenant_id, usage)

        result = QuoteAssistantResult(
            quote_id=quote_id,
            scope=scope,
            matched_tasks=outcome.matched_tasks,
            model_id=usage.model_id,
            tokens_used=usage.tokens_used,
            input_kind=InputKind.OCR,
        )
        events = [
            quote_drafted(
                tenant_id,
                quote_id=quote_id,
                model_id=usage.model_id,
                input_kind=InputKind.OCR.value,
                tokens_used=usage.tokens_used,
                actor_id=user_id,
            ),
            usage_recorded(
                tenant_id,
                feature=usage.feature.value,
                model_id=usage.model_id,
                cost_minor=usage.cost_minor,
                tokens_used=usage.tokens_used,
                actor_id=user_id,
            ),
        ]
        return result, events
