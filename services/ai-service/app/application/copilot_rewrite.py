"""Use case: rewrite line-item descriptions or scope text in a given tone.

The only copilot use case with no upstream dependency: it receives the text
inline and returns polished text. No quote read, no pricebook, no write path.
"""

from __future__ import annotations

from uuid import UUID

from app.application.scope_writer import normalize_tone
from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, usage_recorded
from app.domain.models import RewriteResult
from app.domain.protocols import AiUsageRepository, TextRewriter


class RewriteUseCase:
    def __init__(
        self,
        rewriter: TextRewriter,
        usage_repo: AiUsageRepository,
        *,
        daily_cap_minor: int = 0,
    ) -> None:
        self._rewriter = rewriter
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
        texts: list[str],
        tone: str = "professional",
        context_hint: str | None = None,
    ) -> tuple[RewriteResult, list[DomainEvent]]:
        self._check_spend_cap(tenant_id)

        # `tone` is interpolated into the system prompt, so it is constrained to
        # a known allowlist here (reusing the scope-writer's normaliser) rather
        # than trusting caller text on an LLM that also sees tenant data.
        rewritten, usage = self._rewriter.rewrite(
            texts, normalize_tone(tone), context_hint
        )
        result = RewriteResult(
            rewritten=tuple(rewritten),
            model_id=usage.model_id,
            tokens_used=usage.tokens_used,
        )

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
