"""Use case: free text -> structured scope -> priced line items -> draft quote."""

from __future__ import annotations

from uuid import UUID

from app.application.line_items import DEFAULT_MARKUP_BPS, build_line_items
from app.domain.errors import DailySpendCapExceededError, ScopeExtractionError
from app.domain.events import DomainEvent, quote_drafted, usage_recorded
from app.domain.models import InputKind, QuoteAssistantResult
from app.domain.protocols import (
    AiUsageRepository,
    PricebookMatcher,
    QuoteCreator,
    ScopeExtractor,
)

_MAX_TITLE_LENGTH = 255

# quote-service's `QuoteCreatedVia` (and `packages/types`) has no value for
# "AI drafted it from typed text" — the options are manual/voice/vision/ocr.
# Rather than mislabel a typed request as "voice" or unilaterally widen a
# contract two other services share, text runs record `manual` here, and the
# AI provenance is carried faithfully by `ai.quote.drafted.inputKind` and the
# ai_usage_log row. Tracked as a follow-up in the M15 spec.
_CREATED_VIA = {InputKind.VOICE: "voice", InputKind.TEXT: "manual"}


class TextToQuoteUseCase:
    """Depends only on ports, so the whole pipeline is testable with fakes."""

    def __init__(
        self,
        extractor: ScopeExtractor,
        matcher: PricebookMatcher,
        quote_creator: QuoteCreator,
        usage_repo: AiUsageRepository,
        *,
        daily_cap_minor: int = 0,
    ) -> None:
        self._extractor = extractor
        self._matcher = matcher
        self._quote_creator = quote_creator
        self._usage_repo = usage_repo
        # 0 disables the cap.
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
        text: str,
        customer_id: UUID,
        property_id: UUID | None = None,
        title: str | None = None,
        trade_hint: str | None = None,
        tax_rate_bps: int = 0,
        default_markup_bps: int = DEFAULT_MARKUP_BPS,
        input_kind: InputKind = InputKind.TEXT,
    ) -> tuple[QuoteAssistantResult, list[DomainEvent]]:
        # Cap first — the point of a spend cap is to not spend the money, so
        # checking after the model call would defeat it.
        self._check_spend_cap(tenant_id)

        scope, usage = self._extractor.extract_scope(text, trade_hint)
        if not scope.tasks:
            raise ScopeExtractionError(
                "no billable tasks could be identified in that description"
            )

        matched_tasks = self._matcher.match(tenant_id, user_id, list(scope.tasks))
        line_items = build_line_items(matched_tasks, default_markup_bps=default_markup_bps)

        quote_id = self._quote_creator.create_quote(
            tenant_id,
            user_id,
            customer_id=customer_id,
            property_id=property_id,
            title=(title or scope.summary)[:_MAX_TITLE_LENGTH],
            created_via=_CREATED_VIA[input_kind],
            tax_rate_bps=tax_rate_bps,
            line_items=line_items,
        )

        # Recorded only after the quote exists: billing a tenant for a run
        # that produced nothing would be the wrong way round.
        self._usage_repo.record(tenant_id, usage)

        result = QuoteAssistantResult(
            quote_id=quote_id,
            scope=scope,
            matched_tasks=tuple(matched_tasks),
            model_id=usage.model_id,
            tokens_used=usage.tokens_used,
            input_kind=input_kind,
        )
        events = [
            quote_drafted(
                tenant_id,
                quote_id=quote_id,
                model_id=usage.model_id,
                input_kind=input_kind.value,
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
