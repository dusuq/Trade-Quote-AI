"""HTTP-level tests for the copilot endpoints. External adapters are faked."""

from __future__ import annotations

import uuid

from tests.fakes import make_snapshot


def _pricing_body(quote_id: str | None = None) -> dict[str, str]:
    return {"quote_id": quote_id or str(uuid.uuid4())}


def test_analyze_pricing_happy_path(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/copilot/analyze-pricing", json=_pricing_body(), headers=auth_header
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["suggestions"]) == len(fake_deps.quote_reader_impl.snapshot.line_items)
    assert "gross_margin_bps" in body["margin"]
    assert body["model_id"] == "claude-sonnet-5"


def test_missing_items_happy_path(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/copilot/missing-items",
        json={"quote_id": str(uuid.uuid4()), "job_description": "200A panel upgrade"},
        headers=auth_header,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trade"] == "electrical"
    assert body["missing"]
    assert 0 <= body["completeness_score"] <= 100


def test_rewrite_happy_path(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/copilot/rewrite",
        json={"texts": ["install 200a panel", "12x LED"], "tone": "friendly"},
        headers=auth_header,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["rewritten"]) == 2


def test_analyze_pricing_quote_not_found_is_404(client, api_session, fake_deps, auth_header) -> None:
    fake_deps.quote_reader_impl.found = False
    response = client.post(
        "/v1/ai/copilot/analyze-pricing", json=_pricing_body(), headers=auth_header
    )
    assert response.status_code == 404


def test_copilot_missing_tenant_is_401(client) -> None:
    assert client.post("/v1/ai/copilot/analyze-pricing", json=_pricing_body()).status_code == 401


def test_copilot_disabled_is_503(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.feature_copilot", False)
    response = client.post(
        "/v1/ai/copilot/rewrite", json={"texts": ["x"]}, headers=auth_header
    )
    assert response.status_code == 503


def test_rewrite_invalid_tone_is_normalized(client, api_session, fake_deps, auth_header) -> None:
    client.post(
        "/v1/ai/copilot/rewrite",
        json={"texts": ["x"], "tone": "pirate"},
        headers=auth_header,
    )
    assert fake_deps.text_rewriter_impl.calls[0][1] == "professional"


def test_empty_texts_rejected_by_validation(client, api_session, fake_deps, auth_header) -> None:
    response = client.post("/v1/ai/copilot/rewrite", json={"texts": []}, headers=auth_header)
    assert response.status_code == 422


def test_copilot_spend_cap_is_429(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.daily_spend_cap_minor", 1)
    # First rewrite books usage; the second trips the cap.
    client.post("/v1/ai/copilot/rewrite", json={"texts": ["x"]}, headers=auth_header)
    response = client.post("/v1/ai/copilot/rewrite", json={"texts": ["y"]}, headers=auth_header)
    assert response.status_code == 429


def test_usage_recorded_under_copilot_feature(client, api_session, fake_deps, auth_header) -> None:
    client.post("/v1/ai/copilot/analyze-pricing", json=_pricing_body(), headers=auth_header)

    usage = client.get("/v1/ai/usage", headers=auth_header).json()

    assert len(usage) == 1
    assert usage[0]["feature"] == "copilot"
    assert usage[0]["model_id"] == "claude-sonnet-5"


def test_empty_quote_pricing_returns_200_with_no_suggestions(
    client, api_session, fake_deps, auth_header
) -> None:
    fake_deps.quote_reader_impl.snapshot = make_snapshot(line_items=())
    response = client.post(
        "/v1/ai/copilot/analyze-pricing", json=_pricing_body(), headers=auth_header
    )
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []
