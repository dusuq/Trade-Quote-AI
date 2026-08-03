"""Core payment / invoice flows — the money-object lifecycle.

Runs with no Stripe/Square credentials configured, so `create_payment_intent`
skips the provider call and creates a local pending row (the offline-testable
path).
"""

from __future__ import annotations

import uuid


def _intent_body(**over) -> dict:
    body = {
        "quote_id": str(uuid.uuid4()),
        "amount_minor": 50_000,
        "currency": "USD",
        "payment_type": "deposit",
        "idempotency_key": str(uuid.uuid4()),
    }
    body.update(over)
    return body


def test_create_intent_starts_pending(client, api_session, auth_header) -> None:
    resp = client.post("/v1/payments/intents", json=_intent_body(), headers=auth_header)

    assert resp.status_code == 201, resp.text
    payment = resp.json()
    assert payment["status"] == "pending"
    assert payment["amount_minor"] == 50_000
    assert payment["captured_at"] is None


def test_created_payment_is_retrievable(client, api_session, auth_header) -> None:
    created = client.post(
        "/v1/payments/intents", json=_intent_body(), headers=auth_header
    ).json()

    got = client.get(f"/v1/payments/{created['id']}", headers=auth_header)

    assert got.status_code == 200
    assert got.json()["id"] == created["id"]


def test_duplicate_idempotency_key_is_409(client, api_session, auth_header) -> None:
    """A retried intent with the same key must not create a second charge."""
    body = _intent_body()
    first = client.post("/v1/payments/intents", json=body, headers=auth_header)
    assert first.status_code == 201

    second = client.post("/v1/payments/intents", json=body, headers=auth_header)
    assert second.status_code == 409


def test_missing_tenant_is_rejected(client, api_session) -> None:
    resp = client.post("/v1/payments/intents", json=_intent_body())
    assert resp.status_code == 401


def test_amount_must_be_positive(client, api_session, auth_header) -> None:
    resp = client.post(
        "/v1/payments/intents", json=_intent_body(amount_minor=0), headers=auth_header
    )
    assert resp.status_code == 422  # Field(gt=0)


def test_invoice_create_then_issue_transitions_status(client, api_session, auth_header) -> None:
    created = client.post(
        "/v1/payments/invoices",
        json={
            "quote_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "subtotal_minor": 100_000,
            "tax_minor": 8_000,
            "total_minor": 108_000,
        },
        headers=auth_header,
    )
    assert created.status_code == 201, created.text
    invoice = created.json()
    assert invoice["status"] == "draft"

    issued = client.post(
        f"/v1/payments/invoices/{invoice['id']}/issue", json={}, headers=auth_header
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "issued"
