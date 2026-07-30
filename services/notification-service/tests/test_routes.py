"""HTTP-level tests. Providers are faked via `fake_deps`; the delivery
BackgroundTask runs synchronously under TestClient, so a queued message is
already delivered by the time we read it back."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

EMAIL_BODY = {
    "channel": "email",
    "recipient": "jane@domain.com",
    "template_name": "quote_delivery",
    "template_vars": {"company_name": "ACME", "customer_name": "Jane", "view_link": "http://x/view"},
}


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "healthy"


def test_send_returns_202_with_queued_message(client, api_session, fake_deps, auth_header) -> None:
    response = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["channel"] == "email"
    assert body["to_redacted"] == "j***e@domain.com"
    assert "recipient" not in body  # raw address never returned


def test_send_dispatches_and_marks_sent(client, api_session, fake_deps, auth_header) -> None:
    created = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header).json()

    # BackgroundTask has run: the fake provider was called and the row is 'sent'.
    assert len(fake_deps.email.sent) == 1
    fetched = client.get(f"/v1/notifications/logs/{created['id']}", headers=auth_header).json()
    assert fetched["status"] == "sent"
    assert fetched["provider"] == "console"
    assert fetched["provider_message_id"] is not None


def test_send_sms_uses_sms_provider(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/notifications/send",
        json={
            "channel": "sms",
            "recipient": "+14155552671",
            "template_name": "quote_delivery",
            "template_vars": {"company_name": "ACME", "view_link": "http://x"},
        },
        headers=auth_header,
    )
    assert response.status_code == 202
    assert len(fake_deps.sms.sent) == 1
    assert fake_deps.email.sent == []


def test_send_unknown_channel_is_422(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/notifications/send",
        json={**EMAIL_BODY, "channel": "pigeon"},
        headers=auth_header,
    )
    assert response.status_code == 422


def test_send_bad_recipient_is_422(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/notifications/send",
        json={**EMAIL_BODY, "recipient": "no-at-sign"},
        headers=auth_header,
    )
    assert response.status_code == 422


def test_send_unknown_template_is_404(client, api_session, fake_deps, auth_header) -> None:
    response = client.post(
        "/v1/notifications/send",
        json={**EMAIL_BODY, "template_name": "does_not_exist"},
        headers=auth_header,
    )
    assert response.status_code == 404


def test_missing_tenant_header_is_401(client: TestClient) -> None:
    assert client.post("/v1/notifications/send", json=EMAIL_BODY).status_code == 401


def test_invalid_tenant_header_is_400(client: TestClient) -> None:
    response = client.post(
        "/v1/notifications/send", json=EMAIL_BODY, headers={"x-tenant-id": "not-a-uuid"}
    )
    assert response.status_code == 400


def test_logs_endpoint_lists_messages(client, api_session, fake_deps, auth_header) -> None:
    client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header)
    logs = client.get("/v1/notifications/logs", headers=auth_header).json()
    assert len(logs) == 1
    assert logs[0]["template_name"] == "quote_delivery"


def test_log_not_found_is_404(client, api_session, fake_deps, auth_header) -> None:
    response = client.get(f"/v1/notifications/logs/{uuid.uuid4()}", headers=auth_header)
    assert response.status_code == 404


def test_upsert_and_list_templates(client, api_session, fake_deps, auth_header) -> None:
    create = client.post(
        "/v1/notifications/templates",
        json={
            "name": "quote_delivery",
            "channel": "email",
            "subject_template": "Custom subject",
            "body_template": "<p>Hi {{ customer_name }}</p>",
        },
        headers=auth_header,
    )
    assert create.status_code == 201, create.text

    listed = client.get("/v1/notifications/templates", headers=auth_header).json()
    assert len(listed) == 1
    assert listed[0]["subject_template"] == "Custom subject"


def test_custom_template_is_used_on_send(client, api_session, fake_deps, auth_header) -> None:
    client.post(
        "/v1/notifications/templates",
        json={
            "name": "quote_delivery",
            "channel": "email",
            "subject_template": "Overridden",
            "body_template": "<p>custom body</p>",
        },
        headers=auth_header,
    )
    created = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header).json()
    fetched = client.get(f"/v1/notifications/logs/{created['id']}", headers=auth_header).json()
    assert fetched["subject"] == "Overridden"
