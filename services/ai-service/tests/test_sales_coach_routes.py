"""HTTP-level tests for the sales-coach endpoint. External adapters are faked
via `fake_deps`, same pattern as `test_copilot_routes.py`."""

from __future__ import annotations

import uuid

from tests.fakes import make_sales_suggestion


def _body() -> dict:
    return {"quote_id": str(uuid.uuid4())}


def test_sales_coach_happy_path(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["suggestions"]
    assert body["suggestions"][0]["kind"] == "cross_sell"
    assert "quote_id" in body


def test_sales_coach_never_creates_or_modifies_a_quote(
    client, api_session, fake_deps, auth_header
) -> None:
    client.post("/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header)

    assert fake_deps.quote_creator_impl.calls == []


def test_empty_suggestions_is_a_200_not_an_error(
    client, api_session, fake_deps, auth_header
) -> None:
    fake_deps.sales_coach_analyzer_impl.suggestions = ()

    response = client.post(
        "/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header
    )

    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []


def test_quote_not_found_is_404(client, api_session, fake_deps, auth_header) -> None:
    fake_deps.quote_reader_impl.found = False

    response = client.post(
        "/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header
    )

    assert response.status_code == 404


def test_sales_coach_disabled_is_503(
    client, api_session, fake_deps, auth_header, monkeypatch
) -> None:
    monkeypatch.setattr("app.interface.routes.settings.feature_ai_sales_coach", False)

    response = client.post(
        "/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header
    )

    assert response.status_code == 503


def test_missing_tenant_header_is_401(client) -> None:
    response = client.post("/v1/ai/sales-coach/suggest", json=_body())
    assert response.status_code == 401


def test_spend_cap_returns_429(
    client, api_session, fake_deps, auth_header, monkeypatch
) -> None:
    monkeypatch.setattr("app.interface.routes.settings.daily_spend_cap_minor", 1)
    client.post("/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header)

    response = client.post(
        "/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header
    )

    assert response.status_code == 429


def test_multiple_suggestions_all_appear_and_estimated_price_is_optional(
    client, api_session, fake_deps, auth_header
) -> None:
    fake_deps.sales_coach_analyzer_impl.suggestions = (
        make_sales_suggestion("Whole-home surge protector"),
        make_sales_suggestion("5-year extended warranty", estimated_price_minor=None),
    )

    response = client.post(
        "/v1/ai/sales-coach/suggest", json=_body(), headers=auth_header
    )

    body = response.json()
    assert len(body["suggestions"]) == 2
    assert body["suggestions"][1]["estimated_price_minor"] is None
