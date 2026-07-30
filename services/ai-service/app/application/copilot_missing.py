"""Use case: read a quote and ask the LLM what's missing for the trade.

Read-only, like the rest of the copilot. No pricebook lookup and no
service-to-service write path — just a quote read plus one model call.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, usage_recorded
from app.domain.models import MissingItemsResult
from app.domain.protocols import AiUsageRepository, CopilotAnalyzer, QuoteReader


class FindMissingItemsUseCase:
    def __init__(
        self,
        quote_reader: QuoteReader,
        analyzer: CopilotAnalyzer,
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
        job_description: str | None = None,
    ) -> tuple[MissingItemsResult, list[DomainEvent]]:
        self._check_spend_cap(tenant_id)

        quote = self._quote_reader.get_quote(tenant_id, user_id, quote_id)
        result, usage = self._analyzer.find_missing_items(quote, job_description)

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
