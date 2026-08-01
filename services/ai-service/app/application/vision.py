"""Shared vision-pipeline plumbing: photo -> detection -> pricebook match.

Both `EquipmentDetectionUseCase` (detect-only "material list") and
`VisionToQuoteUseCase` (photo straight to a draft quote) need the same
detect-then-match step; this module is the one place it happens so the two
flows can't drift apart (same reasoning as `application/line_items.py`'s
docstring for the text/voice pipeline).
"""

from __future__ import annotations

from uuid import UUID

from app.domain.errors import EquipmentDetectionError
from app.domain.models import (
    AiUsage,
    EquipmentDetectionOutcome,
    EquipmentDetectionResult,
    ExtractedScope,
    ExtractedTask,
)
from app.domain.protocols import PricebookMatcher, VisionDetector

# Conditions worth flagging in the line-item description itself — "worn" or
# "damaged" equipment usually means the contractor is quoting a replacement,
# and that context is easy to lose once the task becomes a bare line item.
_FLAGGED_CONDITIONS = frozenset({"worn", "damaged"})


def equipment_to_extracted_scope(result: EquipmentDetectionResult) -> ExtractedScope:
    """Map a vision detection onto the same `ExtractedScope` shape the
    text/voice pipeline produces, so `build_line_items` and `PricebookMatcher`
    need no vision-specific branch."""
    tasks = tuple(
        ExtractedTask(
            description=(
                f"{item.name} (condition: {item.condition.value})"
                if item.condition.value in _FLAGGED_CONDITIONS
                else item.name
            ),
            category=item.category,
            item_name=item.name,
            quantity=item.quantity,
            unit=item.unit,
        )
        for item in result.equipment
    )
    return ExtractedScope(
        trade=result.trade,
        summary=result.summary,
        tasks=tasks,
        notes=result.notes,
    )


def detect_and_match(
    detector: VisionDetector,
    matcher: PricebookMatcher,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    image_bytes: bytes,
    mime_type: str,
    trade_hint: str | None = None,
) -> tuple[EquipmentDetectionOutcome, ExtractedScope, AiUsage]:
    """Run detection then pricebook matching.

    Returns the outcome, the intermediate `ExtractedScope` (what
    `build_line_items` needs when the caller goes on to create a quote), and
    the raw `AiUsage` (what the caller needs to record spend — deliberately
    not folded into the outcome, since usage recording has its own timing
    rules; see `VisionToQuoteUseCase`).
    """
    detection, usage = detector.detect_equipment(image_bytes, mime_type, trade_hint)
    if not detection.equipment:
        raise EquipmentDetectionError(
            "no equipment could be identified in that photo"
        )

    scope = equipment_to_extracted_scope(detection)
    matched_tasks = matcher.match(tenant_id, user_id, list(scope.tasks))

    outcome = EquipmentDetectionOutcome(
        detection=detection,
        matched_tasks=tuple(matched_tasks),
        model_id=usage.model_id,
        tokens_used=usage.tokens_used,
    )
    return outcome, scope, usage
