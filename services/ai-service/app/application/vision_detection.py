"""Use case: photo -> equipment detection -> matched material list.

No quote is created here — this is the "point the camera at the panel and see
what's there" flow. `VisionToQuoteUseCase` builds on the same detect-and-match
step to go all the way to a draft quote.
"""

from __future__ import annotations

from uuid import UUID

from app.application.image import validate_image
from app.application.vision import detect_and_match
from app.domain.errors import DailySpendCapExceededError
from app.domain.events import DomainEvent, usage_recorded
from app.domain.models import EquipmentDetectionOutcome
from app.domain.protocols import AiUsageRepository, PricebookMatcher, VisionDetector


class EquipmentDetectionUseCase:
    def __init__(
        self,
        detector: VisionDetector,
        matcher: PricebookMatcher,
        usage_repo: AiUsageRepository,
        *,
        max_image_bytes: int,
        daily_cap_minor: int = 0,
    ) -> None:
        self._detector = detector
        self._matcher = matcher
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
        trade_hint: str | None = None,
    ) -> tuple[EquipmentDetectionOutcome, DomainEvent]:
        # Cap first, same reasoning as text_to_quote.py: check before spending.
        self._check_spend_cap(tenant_id)

        normalized_mime = validate_image(
            size_bytes=len(image_bytes),
            mime_type=mime_type,
            max_bytes=self._max_image_bytes,
        )

        outcome, _scope, usage = detect_and_match(
            self._detector,
            self._matcher,
            tenant_id=tenant_id,
            user_id=user_id,
            image_bytes=image_bytes,
            mime_type=normalized_mime,
            trade_hint=trade_hint,
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
