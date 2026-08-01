"""HTTP-level tests for the OCR endpoints. External adapters are faked via
`fake_deps`, same pattern as `test_vision_routes.py`."""

from __future__ import annotations

import uuid

from tests.fakes import make_document_result, make_match, make_ocr_line_item

CUSTOMER = str(uuid.uuid4())


def test_extract_document_returns_the_line_items(client, api_session, fake_deps, auth_header) -> None:
    fake_deps.pricebook_matcher.matches = {"3/4in copper pipe": make_match()}

    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document_kind"] == "invoice"
    assert body["vendor_name"] == "Acme Supply Co."
    assert len(body["line_items"]) == 1
    assert body["line_items"][0]["pricebook_item_id"] is not None
    assert body["unmatched_count"] == 0


def test_extract_document_does_not_create_a_quote(client, api_session, fake_deps, auth_header) -> None:
    client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert fake_deps.quote_creator_impl.calls == []


def test_ocr_to_quote_creates_a_draft_quote(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/ocr-to-quote",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        data={"customer_id": CUSTOMER},
        headers=auth_header,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["input_kind"] == "ocr"
    assert body["trade"] == "plumbing"
    assert fake_deps.quote_creator_impl.calls[0]["created_via"] == "ocr"


def test_oversized_document_is_413(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.max_document_size_bytes", 10)

    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 413


def test_unsupported_document_format_is_400(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
        headers=auth_header,
    )

    assert response.status_code == 400


def test_no_line_items_extracted_is_422(client, api_session, fake_deps, auth_header) -> None:
    fake_deps.document_extractor_impl.extraction = make_document_result(line_items=())

    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 422


def test_ocr_disabled_is_503(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.feature_ai_ocr", False)

    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 503


def test_missing_tenant_header_is_401(client) -> None:
    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
    )
    assert response.status_code == 401


def test_spend_cap_returns_429(client, api_session, fake_deps, auth_header, monkeypatch) -> None:
    monkeypatch.setattr("app.interface.routes.settings.daily_spend_cap_minor", 1)
    client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    assert response.status_code == 429


def test_multiple_line_items_all_appear_in_the_response(
    client, api_session, fake_deps, auth_header
) -> None:
    fake_deps.document_extractor_impl.extraction = make_document_result(
        (make_ocr_line_item("Copper pipe"), make_ocr_line_item("Coupling", quantity="6"))
    )

    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    body = response.json()
    assert len(body["line_items"]) == 2
    assert body["line_items"][1]["quantity"] == "6"


def test_extracted_unit_cost_is_exposed_alongside_the_pricebook_cost(
    client, api_session, fake_deps, auth_header
) -> None:
    """The invoice's own price and the pricebook's price are both surfaced so
    the contractor can compare them — see M19's cost-injection reasoning."""
    fake_deps.pricebook_matcher.matches = {
        "3/4in copper pipe": make_match(unit_cost_minor=500)
    }

    response = client.post(
        "/v1/ai/ocr/extract",
        files={"document": ("invoice.jpg", b"x" * 500, "image/jpeg")},
        headers=auth_header,
    )

    item = response.json()["line_items"][0]
    assert item["extracted_unit_cost_minor"] == 1_200
    assert item["unit_cost_minor"] == 500
