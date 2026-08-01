"""Vision-pipeline plumbing: scope conversion and detect-then-match."""

from __future__ import annotations

import uuid

import pytest

from app.application.vision import detect_and_match, equipment_to_extracted_scope
from app.domain.errors import EquipmentDetectionError
from app.domain.models import EquipmentCondition, TaskCategory
from tests.fakes import (
    FakePricebookMatcher,
    FakeVisionDetector,
    make_detection,
    make_equipment,
)

TENANT = uuid.uuid4()


def test_condition_is_flagged_in_the_description_when_worn_or_damaged() -> None:
    detection = make_detection(
        (make_equipment("Service panel", condition=EquipmentCondition.DAMAGED),)
    )

    scope = equipment_to_extracted_scope(detection)

    assert "condition: damaged" in scope.tasks[0].description


def test_good_condition_is_not_mentioned_in_the_description() -> None:
    detection = make_detection((make_equipment("Service panel", condition=EquipmentCondition.GOOD),))

    scope = equipment_to_extracted_scope(detection)

    assert scope.tasks[0].description == "Service panel"


def test_scope_carries_trade_and_notes_through() -> None:
    detection = make_detection()

    scope = equipment_to_extracted_scope(detection)

    assert scope.trade == detection.trade
    assert scope.notes == detection.notes


def test_detect_and_match_runs_detection_then_matching() -> None:
    detector = FakeVisionDetector()
    matcher = FakePricebookMatcher()

    outcome, scope, usage = detect_and_match(
        detector,
        matcher,
        tenant_id=TENANT,
        user_id=None,
        image_bytes=b"x" * 100,
        mime_type="image/jpeg",
    )

    assert detector.calls == [(100, "image/jpeg", None)]
    assert len(matcher.calls) == 1
    assert len(outcome.matched_tasks) == len(scope.tasks)
    assert usage.tokens_used == detector.tokens


def test_empty_equipment_list_is_rejected() -> None:
    detector = FakeVisionDetector(make_detection(equipment=()))
    matcher = FakePricebookMatcher()

    with pytest.raises(EquipmentDetectionError, match="no equipment"):
        detect_and_match(
            detector,
            matcher,
            tenant_id=TENANT,
            user_id=None,
            image_bytes=b"x" * 10,
            mime_type="image/jpeg",
        )


def test_labor_category_survives_conversion() -> None:
    detection = make_detection(
        (make_equipment("Replace damaged flashing", category=TaskCategory.LABOR),)
    )

    scope = equipment_to_extracted_scope(detection)

    assert scope.tasks[0].category == TaskCategory.LABOR
