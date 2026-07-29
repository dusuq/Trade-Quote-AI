"""HTTP-level tests. Every external adapter is faked via `fake_deps`."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.fakes import make_match, make_scope

CUSTOMER = str(uuid.uuid4())
TEXT_BODY = {
    "text": "Replace the panel with a 200 amp and install twelve LED lights",
    "customer_id": CUSTOMER,
}


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "healthy"


def test_text_to_quote_returns_the_draft(client, api_session, fake_deps, auth_header) -> None:
    fake_deps.pricebook_matcher.matches = {"200A main breaker panel": make_match()}

    response = client.post("/v1/ai/text-to-quote", json=TEXT_BODY, headers=auth_header)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["trade"] == "electrical"
    assert body["input_kind"] == "text"
    assert len(body["tasks"]) == 2
    assert body["unmatched_count"] == 1
    assert body["tasks"][0]["pricebook_item_id"] is not None
    assert body["tasks"][1]["pricebook_item_id"] is None


def test_missing_tenant_header_is_401(client: TestClient) -> None:
    assert client.post("/v1/ai/text-to-quote", json=TEXT_BODY).status_code == 401


def test_invalid_tenant_header_is_400(client: TestClient) -> None:
    response = client.post(
        "/v1/ai/text-to-quote", json=TEXT_BODY, headers={"x-tenant-id": "not-a-uuid"}
    )
    assert response.status_code == 400


def test_short_text_is_rejected_by_validation(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/text-to-quote", json={**TEXT_BODY, "text": "fix it"}, headers=auth_header
    )
    assert response.status_code == 422


def test_scope_with_no_tasks_is_422(client, api_session, fake_deps, auth_header) -> None:
    fake_deps.scope_extractor.scope = make_scope(tasks=())

    response = client.post("/v1/ai/text-to-quote", json=TEXT_BODY, headers=auth_header)

    assert response.status_code == 422


def test_voice_to_quote_accepts_an_upload(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/voice-to-quote",
        files={"audio": ("clip.webm", b"x" * 500, "audio/webm")},
        data={"customer_id": CUSTOMER},
        headers=auth_header,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["input_kind"] == "voice"
    assert body["transcript"] == "Replace the panel with a 200 amp"
    assert body["language"] == "en"


def test_oversized_audio_is_413(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.max_audio_size_bytes", 10)

    response = client.post(
        "/v1/ai/voice-to-quote",
        files={"audio": ("clip.webm", b"x" * 500, "audio/webm")},
        data={"customer_id": CUSTOMER},
        headers=auth_header,
    )

    assert response.status_code == 413


def test_unsupported_audio_format_is_400(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/voice-to-quote",
        files={"audio": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
        data={"customer_id": CUSTOMER},
        headers=auth_header,
    )

    assert response.status_code == 400


def test_spend_cap_returns_429(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.daily_spend_cap_minor", 1)
    # Seed a usage row so today's spend is already at the cap.
    client.post("/v1/ai/text-to-quote", json=TEXT_BODY, headers=auth_header)

    response = client.post("/v1/ai/text-to-quote", json=TEXT_BODY, headers=auth_header)

    assert response.status_code == 429


def test_scope_writer_returns_prose(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/scope-writer",
        json={
            "trade": "electrical",
            "summary": "Panel upgrade",
            "tasks": [
                {
                    "description": "200A panel",
                    "category": "material",
                    "item_name": "200A main breaker panel",
                    "quantity": 1,
                    "unit": "each",
                }
            ],
            "tone": "friendly",
        },
        headers=auth_header,
    )

    assert response.status_code == 200, response.text
    assert response.json()["scope_text"].startswith("We will replace")
    assert fake_deps.scope_narrator.calls[0][1] == "friendly"


def test_scope_writer_requires_at_least_one_task(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/scope-writer",
        json={"trade": "electrical", "summary": "x", "tasks": []},
        headers=auth_header,
    )
    assert response.status_code == 422


def test_usage_endpoint_lists_recorded_calls(client, api_session, fake_deps, auth_header) -> None:
    client.post("/v1/ai/text-to-quote", json=TEXT_BODY, headers=auth_header)

    body = client.get("/v1/ai/usage", headers=auth_header).json()

    assert len(body) == 1
    assert body[0]["model_id"] == "claude-opus-5"
    assert body[0]["tokens_used"] == 1_200
    assert isinstance(body[0]["cost_minor"], int)


def test_usage_endpoint_is_empty_before_any_calls(client, api_session, auth_header) -> None:
    assert client.get("/v1/ai/usage", headers=auth_header).json() == []
