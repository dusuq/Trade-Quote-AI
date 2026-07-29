"""Use case: structured scope -> customer-facing scope-of-work prose."""

from __future__ import annotations

from uuid import UUID

from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, usage_recorded
from app.domain.models import AiUsage, ExtractedScope
from app.domain.protocols import AiUsageRepository, ScopeNarrator

ALLOWED_TONES: frozenset[str] = frozenset({"professional", "friendly", "technical", "concise"})
DEFAULT_TONE = "professional"


def normalize_tone(tone: str | None) -> str:
    """Constrain tone to a known set.

    `tone` is interpolated into the system prompt, so accepting arbitrary
    caller text would be a prompt-injection surface on an LLM that also sees
    tenant data. An allowlist closes that off.
    """
    if not tone:
        return DEFAULT_TONE
    candidate = tone.strip().lower()
    return candidate if candidate in ALLOWED_TONES else DEFAULT_TONE


class ScopeWriterUseCase:
    def __init__(
        self,
        narrator: ScopeNarrator,
        usage_repo: AiUsageRepository,
        *,
        daily_cap_minor: int = 0,
    ) -> None:
        self._narrator = narrator
        self._usage_repo = usage_repo
        self._daily_cap_minor = daily_cap_minor

    def execute(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        scope: ExtractedScope,
        tone: str | None = DEFAULT_TONE,
    ) -> tuple[str, AiUsage, DomainEvent]:
        if self._daily_cap_minor > 0:
            spent = self._usage_repo.spend_today_minor(tenant_id)
            if spent >= self._daily_cap_minor:
                raise DailySpendCapExceededError(
                    f"daily AI spend cap reached ({spent} of {self._daily_cap_minor} minor units)"
                )

        scope_text, usage = self._narrator.write_scope(scope, normalize_tone(tone))
        self._usage_repo.record(tenant_id, usage)

        event = usage_recorded(
            tenant_id,
            feature=usage.feature.value,
            model_id=usage.model_id,
            tokens_used=usage.tokens_used,
            cost_minor=usage.cost_minor,
            actor_id=user_id,
        )
        return scope_text, usage, event
