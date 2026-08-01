"""Use case: read a quote and ask the LLM what else is worth offering the
customer — an upsell, a warranty/maintenance add-on, or a cross-sell.

Read-only, like the rest of the copilot family (`copilot_missing.py`,
`copilot_pricing.py`): no pricebook lookup, no write path — just a quote read
plus one model call.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, usage_recorded
from app.domain.models import SalesCoachResult
from app.domain.protocols import AiUsageRepository, QuoteReader, SalesCoachAnalyzer


class SalesCoachUseCase:
    def __init__(
        self,
        quote_reader: QuoteReader,
        analyzer: SalesCoachAnalyzer,
        usage_repo: AiUsageRepository,
        *,
        daily_cap_minor: int = 0,
    ) -> None:
        self._quote_reader = quote_reader
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

    def execute(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        quote_id: UUID,
    ) -> tuple[SalesCoachResult, list[DomainEvent]]:
        self._check_spend_cap(tenant_id)

        quote = self._quote_reader.get_quote(tenant_id, user_id, quote_id)
        result, usage = self._analyzer.suggest(quote)

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
