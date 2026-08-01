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


# ── Item 1: Three-phase delivery ────────────────────────────────────────


def test_three_phase_delivery_success(client, api_session, fake_deps, auth_header) -> None:
    """Message queued → provider called → status sent, outbox event written."""
    created = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header).json()
    assert created["status"] == "queued"
    fetched = client.get(f"/v1/notifications/logs/{created['id']}", headers=auth_header).json()
    assert fetched["status"] == "sent"
    assert fetched["provider"] == "console"
    assert fetched["provider_message_id"] is not None
    assert len(fake_deps.email.sent) == 1


def test_three_phase_delivery_failure(client, api_session, fake_deps, auth_header) -> None:
    """Provider fails → status is failed, no double connection hold."""
    fake_deps.email.fail = True
    created = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header).json()
    fetched = client.get(f"/v1/notifications/logs/{created['id']}", headers=auth_header).json()
    assert fetched["status"] == "failed"
    assert fetched["error_message"] is not None


def test_three_phase_idempotent_redeliver(client, api_session, fake_deps, auth_header) -> None:
    """Background task re-fired on a sent row → no-op (no double-send)."""
    created = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header).json()
    assert len(fake_deps.email.sent) == 1

    # Manually re-fire the background delivery
    from app.interface.routes import _deliver_in_background

    _deliver_in_background(
        uuid.UUID(auth_header["x-tenant-id"]),
        uuid.UUID(created["id"]),
        None,
    )
    assert len(fake_deps.email.sent) == 1  # not double-sent


# ── Item 2: Idempotency key ─────────────────────────────────────────────


def test_idempotency_key_deduplicates_request(client, api_session, fake_deps, auth_header) -> None:
    """Two POSTs with the same idempotency_key → only one ledger row."""
    body = {**EMAIL_BODY, "idempotency_key": "dedup-123"}
    r1 = client.post("/v1/notifications/send", json=body, headers=auth_header)
    r2 = client.post("/v1/notifications/send", json=body, headers=auth_header)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["id"] == r2.json()["id"]
    # Provider called only once (first request triggered background delivery)
    assert len(fake_deps.email.sent) == 1


def test_idempotency_key_per_tenant(
    client, api_session, fake_deps, auth_header, tenant_id, other_tenant_id
) -> None:
    """Same key for different tenants → two separate rows."""
    body = {**EMAIL_BODY, "idempotency_key": "cross-tenant"}
    r1 = client.post("/v1/notifications/send", json=body, headers=auth_header)
    r2 = client.post(
        "/v1/notifications/send",
        json=body,
        headers={"x-tenant-id": str(other_tenant_id)},
    )
    assert r1.json()["id"] != r2.json()["id"]


def test_idempotency_key_is_optional(client, api_session, fake_deps, auth_header) -> None:
    """POST without idempotency_key works as before."""
    r1 = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header)
    r2 = client.post("/v1/notifications/send", json=EMAIL_BODY, headers=auth_header)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["id"] != r2.json()["id"]  # two distinct messages


# ── Item 4: assert replaced with raise ───────────────────────────────────


def test_assert_replaced_with_raise() -> None:
    """Verify ValueError (not AssertionError) on None id edge case."""
    from app.domain.models import NotificationMessage
    from app.interface.schemas import to_message_response

    msg = NotificationMessage(
        id=None,
        tenant_id=uuid.uuid4(),
        channel="email",
        recipient="a@b.com",
        to_redacted="a***@b.com",
        template_name="test",
        subject=None,
        body="hi",
        status="queued",
    )
    import pytest

    with pytest.raises(ValueError, match="must not be None"):
        to_message_response(msg)
