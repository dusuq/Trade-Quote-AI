"""Use case: photo -> equipment detection -> priced line items -> draft quote.

Mirrors `text_to_quote.py`'s pipeline shape (cap check -> extract -> match ->
build line items -> create quote -> record usage) with the extraction step
replaced by `application.vision.detect_and_match`.
"""

from __future__ import annotations

from uuid import UUID

from app.application.image import validate_image
from app.application.line_items import DEFAULT_MARKUP_BPS, build_line_items
from app.application.vision import detect_and_match
from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, quote_drafted, usage_recorded
from app.domain.models import InputKind, QuoteAssistantResult
from app.domain.protocols import (
    AiUsageRepository,
    PricebookMatcher,
    QuoteCreator,
    VisionDetector,
)

_MAX_TITLE_LENGTH = 255
_CREATED_VIA = "vision"


class VisionToQuoteUseCase:
    def __init__(
        self,
        detector: VisionDetector,
        matcher: PricebookMatcher,
        quote_creator: QuoteCreator,
        usage_repo: AiUsageRepository,
        *,
        max_image_bytes: int,
        daily_cap_minor: int = 0,
    ) -> None:
        self._detector = detector
        self._matcher = matcher
        self._quote_creator = quote_creator
        self._usage_repo = usage_repo
        self._max_image_bytes = max_image_bytes
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
        image_bytes: bytes,
        mime_type: str,
        customer_id: UUID,
        property_id: UUID | None = None,
        title: str | None = None,
        trade_hint: str | None = None,
        tax_rate_bps: int = 0,
        default_markup_bps: int = DEFAULT_MARKUP_BPS,
    ) -> tuple[QuoteAssistantResult, list[DomainEvent]]:
        self._check_spend_cap(tenant_id)

        normalized_mime = validate_image(
            size_bytes=len(image_bytes),
            mime_type=mime_type,
            max_bytes=self._max_image_bytes,
        )

        outcome, scope, usage = detect_and_match(
            self._detector,
            self._matcher,
            tenant_id=tenant_id,
            user_id=user_id,
            image_bytes=image_bytes,
            mime_type=normalized_mime,
            trade_hint=trade_hint,
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
            input_kind=InputKind.VISION,
        )
        events = [
            quote_drafted(
                tenant_id,
                quote_id=quote_id,
                model_id=usage.model_id,
                input_kind=InputKind.VISION.value,
                tokens_used=usage.tokens_used,
                actor_id=user_id,
            ),
            usage_recorded(
                tenant_id,
                feature=usage.feature.value,
                model_id=usage.model_id,
                tokens_used=usage.tokens_used,
                cost_minor=usage.cost_minor,
                actor_id=user_id,
            ),
        ]
        return result, events
