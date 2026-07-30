"""Use case: read a quote, gather pricebook context, analyze pricing + margin.

Read-only. This never writes to quote-service (M16 plan §Key Design Decisions
#1) — it returns advice the contractor applies by hand.
"""

from __future__ import annotations

from uuid import UUID

from app.application.margin import compute_margin
from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, usage_recorded
from app.domain.models import (
    ExtractedTask,
    PricebookMatch,
    PricingAnalysisResult,
    QuoteLineItem,
    QuoteSnapshot,
    TaskCategory,
)
from app.domain.protocols import (
    AiUsageRepository,
    CopilotAnalyzer,
    PricebookMatcher,
    QuoteReader,
)


def _as_task(item: QuoteLineItem) -> ExtractedTask:
    """Turn a quote line into a matcher query.

    The matcher (reused from T201) keys off `item_name` + `category`; a quote
    line's `kind` may be a value the extractor's narrower `TaskCategory` doesn't
    carry (e.g. "consumable"), so anything outside the three canonical kinds
    searches as a material — the worst case is a slightly looser search filter.
    """
    try:
        category = TaskCategory(item.kind)
    except ValueError:
        category = TaskCategory.MATERIAL
    return ExtractedTask(
        description=item.description,
        category=category,
        item_name=item.description,
        quantity=item.quantity,
        unit=item.unit,
    )


class AnalyzePricingUseCase:
    """Depends only on ports, so the whole flow is testable with fakes."""

    def __init__(
        self,
        quote_reader: QuoteReader,
        matcher: PricebookMatcher,
        analyzer: CopilotAnalyzer,
        usage_repo: AiUsageRepository,
        *,
        daily_cap_minor: int = 0,
    ) -> None:
        self._quote_reader = quote_reader
        self._matcher = matcher
        self._analyzer = analyzer
        self._usage_repo = usage_repo
        self._daily_cap_minor = daily_cap_minor

    def _check_spend_cap(self, tenant_id: UUID) -> None:
        if self._daily_cap_minor <= 0:
            return
        spent = self._usage_repo.spend_today_minor(tenant_id)
        if spent >= self._daily_cap_minor:
            raise DailySpendCapExceededError(
                f"daily AI spend cap reached ({spent} of {self._daily_cap_minor} minor units)"
            )

    def _pricebook_matches(
        self, tenant_id: UUID, user_id: UUID | None, quote: QuoteSnapshot
    ) -> dict[UUID, PricebookMatch]:
        """Look up each line's current pricebook cost, keyed by line-item id."""
        line_ids = [item.id for item in quote.line_items]
        tasks = [_as_task(item) for item in quote.line_items]
        matched = self._matcher.match(tenant_id, user_id, tasks)
        return {
            line_id: result.match
            for line_id, result in zip(line_ids, matched, strict=True)
            if result.match is not None
        }

    def execute(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        quote_id: UUID,
    ) -> tuple[PricingAnalysisResult, list[DomainEvent]]:
        # Cap first — the point of a spend cap is to not spend the money.
        self._check_spend_cap(tenant_id)

        quote = self._quote_reader.get_quote(tenant_id, user_id, quote_id)

        if not quote.line_items:
            # Nothing to price. Return an honest empty analysis (zeroed margin)
            # without spending a model call or billing the tenant.
            empty = PricingAnalysisResult(
                suggestions=(),
                margin=compute_margin(quote, "This quote has no line items to analyze yet."),
                model_id="",
                tokens_used=0,
            )
            return empty, []

        matches = self._pricebook_matches(tenant_id, user_id, quote)
        result, usage = self._analyzer.analyze_pricing(quote, matches)

        self._usage_repo.record(tenant_id, usage)
        events = [
            usage_recorded(
                tenant_id,
                feature=usage.feature.value,
                model_id=usage.model_id,
                tokens_used=usage.tokens_used,
                cost_minor=usage.cost_minor,
                actor_id=user_id,
            )
        ]
        return result, events
