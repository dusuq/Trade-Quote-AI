"""Use case: document -> structured extraction -> matched line items.

No quote is created here — this is the "photograph the invoice/blueprint/
note and review what was read" flow. `OcrToQuoteUseCase` builds on the same
extract-and-match step to go all the way to a draft quote.
"""

from __future__ import annotations

from uuid import UUID

from app.application.document import validate_document
from app.application.ocr import extract_and_match
from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, usage_recorded
from app.domain.models import OcrExtractionOutcome
from app.domain.protocols import AiUsageRepository, DocumentExtractor, PricebookMatcher


class DocumentExtractionUseCase:
    def __init__(
        self,
        extractor: DocumentExtractor,
        matcher: PricebookMatcher,
        usage_repo: AiUsageRepository,
        *,
        max_document_bytes: int,
        daily_cap_minor: int = 0,
    ) -> None:
        self._extractor = extractor
        self._matcher = matcher
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
        document_kind_hint: str | None = None,
    ) -> tuple[OcrExtractionOutcome, DomainEvent]:
        # Cap first, same reasoning as text_to_quote.py: check before spending.
        self._check_spend_cap(tenant_id)

        normalized_mime = validate_document(
            size_bytes=len(document_bytes),
            mime_type=mime_type,
            max_bytes=self._max_document_bytes,
        )

        outcome, _scope, usage = extract_and_match(
            self._extractor,
            self._matcher,
            tenant_id=tenant_id,
            user_id=user_id,
            document_bytes=document_bytes,
            mime_type=normalized_mime,
            document_kind_hint=document_kind_hint,
        )
        self._usage_repo.record(tenant_id, usage)

        event = usage_recorded(
            tenant_id,
            feature=usage.feature.value,
            model_id=usage.model_id,
            tokens_used=usage.tokens_used,
            cost_minor=usage.cost_minor,
            actor_id=user_id,
        )
        return outcome, event
