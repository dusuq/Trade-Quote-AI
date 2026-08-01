"""HTTP-level tests for the vision endpoints. External adapters are faked via
`fake_deps`, same pattern as `test_routes.py`."""

from __future__ import annotations

import uuid

from tests.fakes import make_detection, make_equipment, make_match

CUSTOMER = str(uuid.uuid4())


def test_detect_equipment_returns_the_material_list(
    client, api_session, fake_deps, auth_header
) -> None:
    fake_deps.pricebook_matcher.matches = {"200A main breaker panel": make_match()}

    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trade"] == "electrical"
    assert len(body["equipment"]) == 1
    assert body["equipment"][0]["pricebook_item_id"] is not None
    assert body["unmatched_count"] == 0


def test_detect_equipment_does_not_create_a_quote(
    client, api_session, fake_deps, auth_header
) -> None:
    client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert fake_deps.quote_creator_impl.calls == []


def test_vision_to_quote_creates_a_draft_quote(
    client, api_session, fake_deps, auth_header
) -> None:
    response = client.post(
        "/v1/ai/vision-to-quote",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        data={"customer_id": CUSTOMER},
        headers=auth_header,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["input_kind"] == "vision"
    assert body["trade"] == "electrical"
    assert fake_deps.quote_creator_impl.calls[0]["created_via"] == "vision"


def test_oversized_image_is_413(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.max_image_size_bytes", 10)

    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 413


def test_unsupported_image_format_is_400(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
        headers=auth_header,
    )

    assert response.status_code == 400


def test_no_equipment_detected_is_422(client, api_session, fake_deps, auth_header) -> None:
    fake_deps.vision_detector_impl.detection = make_detection(equipment=())

    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 422


def test_vision_disabled_is_503(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.feature_ai_vision", False)

    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 503


def test_missing_tenant_header_is_401(client) -> None:
    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
    )
    assert response.status_code == 401


def test_spend_cap_returns_429(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.daily_spend_cap_minor", 1)
    client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 429


def test_multiple_equipment_items_all_appear_in_the_response(
    client, api_session, fake_deps, auth_header
) -> None:
    fake_deps.vision_detector_impl.detection = make_detection(
        (make_equipment("Panel"), make_equipment("Breaker", quantity="3"))
    )

    response = client.post(
        "/v1/ai/vision/detect-equipment",
        files={"image": ("panel.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    body = response.json()
    assert len(body["equipment"]) == 2
    assert body["equipment"][1]["quantity"] == "3"
