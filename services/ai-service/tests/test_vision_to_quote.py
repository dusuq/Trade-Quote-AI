"""Photo -> equipment detection -> priced line items -> draft quote."""

from __future__ import annotations

import uuid

import pytest

from app.application.vision_to_quote import VisionToQuoteUseCase
from app.domain.errors import ImageTooLargeError, UnsupportedImageFormatError
from app.domain.models import InputKind
from tests.fakes import (
    FakePricebookMatcher,
    FakeQuoteCreator,
    FakeVisionDetector,
    InMemoryUsageRepository,
    make_detection,
    make_equipment,
    make_match,
)

TENANT = uuid.uuid4()
CUSTOMER = uuid.uuid4()
MAX_BYTES = 1_000


def build(*, max_bytes: int = MAX_BYTES, matches: dict | None = None):
    detector = FakeVisionDetector()
    matcher = FakePricebookMatcher(matches)
    creator = FakeQuoteCreator()
    use_case = VisionToQuoteUseCase(
        detector, matcher, creator, InMemoryUsageRepository(), max_image_bytes=max_bytes
    )
    return use_case, detector, matcher, creator


def run(use_case, *, image: bytes = b"x" * 100, mime: str = "image/jpeg"):
    return use_case.execute(
        tenant_id=TENANT,
        user_id=None,
        image_bytes=image,
        mime_type=mime,
        customer_id=CUSTOMER,
    )


def test_detects_matches_and_creates_a_quote() -> None:
    use_case, detector, matcher, creator = build()

    result, _events = run(use_case)

    assert detector.calls
    assert matcher.calls
    assert result.quote_id == creator.quote_id


def test_vision_runs_are_labelled_as_vision() -> None:
    use_case, _d, _m, creator = build()

    result, events = run(use_case)

    assert result.input_kind is InputKind.VISION
    assert creator.calls[0]["created_via"] == "vision"
    assert events[0].payload["inputKind"] == "vision"


def test_matched_equipment_becomes_a_priced_line_item() -> None:
    equipment_name = "200A main breaker panel"
    detection = make_detection((make_equipment(equipment_name),))
    matches = {equipment_name: make_match(unit_cost_minor=90_000)}
    detector = FakeVisionDetector(detection)
    matcher = FakePricebookMatcher(matches)
    creator = FakeQuoteCreator()
    use_case = VisionToQuoteUseCase(
        detector, matcher, creator, InMemoryUsageRepository(), max_image_bytes=MAX_BYTES
    )

    run(use_case)

    line_items = creator.calls[0]["line_items"]
    assert line_items[0].unit_cost_minor == 90_000


def test_unmatched_equipment_still_becomes_a_zero_cost_line_item() -> None:
    """Same rule as text/voice: don't silently drop equipment the photo
    showed just because the pricebook has no match."""
    use_case, _d, _m, creator = build(matches={})

    run(use_case)

    line_items = creator.calls[0]["line_items"]
    assert line_items[0].unit_cost_minor == 0


def test_oversized_image_is_rejected_before_detection() -> None:
    use_case, detector, _m, _c = build(max_bytes=10)

    with pytest.raises(ImageTooLargeError):
        run(use_case, image=b"x" * 5_000)

    assert detector.calls == []


def test_unsupported_format_is_rejected_before_detection() -> None:
    use_case, detector, _m, _c = build()

    with pytest.raises(UnsupportedImageFormatError):
        run(use_case, mime="application/pdf")

    assert detector.calls == []


def test_usage_is_recorded_only_after_the_quote_exists() -> None:
    detector = FakeVisionDetector()
    matcher = FakePricebookMatcher()
    creator = FakeQuoteCreator()
    usage_repo = InMemoryUsageRepository()
    use_case = VisionToQuoteUseCase(
        detector, matcher, creator, usage_repo, max_image_bytes=MAX_BYTES
    )

    run(use_case)

    assert len(usage_repo.recorded) == 1
    assert usage_repo.recorded[0].feature.value == "vision"
