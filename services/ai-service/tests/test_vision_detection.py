"""Detect-only flow: photo -> equipment + matched material list, no quote."""

from __future__ import annotations

import uuid

import pytest

from app.application.vision_detection import EquipmentDetectionUseCase
from app.domain.errors import (
    DailySpendCapExceededError,
    EquipmentDetectionError,
    ImageTooLargeError,
    UnsupportedImageFormatError,
)
from tests.fakes import (
    FakePricebookMatcher,
    FakeVisionDetector,
    InMemoryUsageRepository,
    make_detection,
)

TENANT = uuid.uuid4()
MAX_BYTES = 1_000


def build(*, max_bytes: int = MAX_BYTES, daily_cap_minor: int = 0, spend_today: int = 0):
    detector = FakeVisionDetector()
    matcher = FakePricebookMatcher()
    usage_repo = InMemoryUsageRepository(spend_today)
    use_case = EquipmentDetectionUseCase(
        detector,
        matcher,
        usage_repo,
        max_image_bytes=max_bytes,
        daily_cap_minor=daily_cap_minor,
    )
    return use_case, detector, matcher, usage_repo


def run(use_case, *, image: bytes = b"x" * 100, mime: str = "image/jpeg"):
    return use_case.execute(
        tenant_id=TENANT, user_id=None, image_bytes=image, mime_type=mime
    )


def test_detects_and_matches_without_creating_a_quote() -> None:
    use_case, detector, matcher, usage_repo = build()

    outcome, event = run(use_case)

    assert detector.calls
    assert matcher.calls
    assert outcome.detection.equipment
    assert len(usage_repo.recorded) == 1
    assert event.payload["feature"] == "vision"


def test_no_quote_creator_is_involved() -> None:
    """Detect-only really means detect-only — the use case has no reference
    to a QuoteCreator at all, so there's nothing to accidentally call."""
    use_case, *_ = build()
    assert not hasattr(use_case, "_quote_creator")


def test_oversized_image_is_rejected_before_detection() -> None:
    use_case, detector, _m, _u = build(max_bytes=10)

    with pytest.raises(ImageTooLargeError):
        run(use_case, image=b"x" * 5_000)

    assert detector.calls == []


def test_unsupported_format_is_rejected_before_detection() -> None:
    use_case, detector, _m, _u = build()

    with pytest.raises(UnsupportedImageFormatError):
        run(use_case, mime="application/pdf")

    assert detector.calls == []


def test_empty_detection_raises_before_matching() -> None:
    detector = FakeVisionDetector(make_detection(equipment=()))
    matcher = FakePricebookMatcher()
    use_case = EquipmentDetectionUseCase(
        detector, matcher, InMemoryUsageRepository(), max_image_bytes=MAX_BYTES
    )

    with pytest.raises(EquipmentDetectionError):
        run(use_case)

    assert matcher.calls == []


def test_spend_cap_blocks_before_the_model_call() -> None:
    use_case, detector, _m, _u = build(daily_cap_minor=10, spend_today=10)

    with pytest.raises(DailySpendCapExceededError):
        run(use_case)

    assert detector.calls == []
