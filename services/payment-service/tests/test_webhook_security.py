"""Webhook security — the vulnerability T303's audit rejected.

Both webhook routes are public and unauthenticated (allowlisted at the
gateway), and both mutate payment state. The pre-fix handlers trusted an
unsigned Stripe body when the secret was unset, and did NO verification at all
for Square — so anyone could POST a forged event and mark a payment captured.

These pin the fail-closed behaviour: no verification, no state change.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

import app.config as app_config


@pytest.fixture(autouse=True)
def _no_capture(monkeypatch: pytest.MonkeyPatch):
    """Fail loudly if any rejection path still reaches capture_payment."""

    def _boom(*_a, **_k):
        raise AssertionError("capture_payment reached on an unverified webhook")

    monkeypatch.setattr("app.interface.routes.capture_payment", _boom)


def test_stripe_webhook_rejects_when_no_secret_configured(client, monkeypatch) -> None:
    monkeypatch.setattr(app_config.settings, "stripe_webhook_secret", "")

    resp = client.post(
        "/v1/payments/webhooks/stripe",
        content=json.dumps(
            {"type": "checkout.session.completed", "data": {"object": {"id": "cs_x"}}}
        ),
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )

    # Fail closed: without the secret we cannot verify, so we refuse.
    assert resp.status_code == 503


def test_stripe_webhook_rejects_a_bad_signature(client, monkeypatch) -> None:
    monkeypatch.setattr(app_config.settings, "stripe_webhook_secret", "whsec_test")

    resp = client.post(
        "/v1/payments/webhooks/stripe",
        content=json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}),
        headers={"stripe-signature": "t=1,v1=forged"},
    )

    assert resp.status_code == 400  # construct_event raises on a bad signature


def test_square_webhook_rejects_when_no_key_configured(client, monkeypatch) -> None:
    monkeypatch.setattr(app_config.settings, "square_webhook_signature_key", "")

    resp = client.post(
        "/v1/payments/webhooks/square",
        content=json.dumps({"type": "payment.completed", "data": {}}),
    )

    assert resp.status_code == 401


def test_square_webhook_rejects_a_missing_signature(client, monkeypatch) -> None:
    monkeypatch.setattr(app_config.settings, "square_webhook_signature_key", "sq_key")

    resp = client.post(
        "/v1/payments/webhooks/square",
        content=json.dumps({"type": "payment.completed", "data": {}}),
    )

    assert resp.status_code == 401


def test_square_webhook_rejects_a_forged_signature(client, monkeypatch) -> None:
    monkeypatch.setattr(app_config.settings, "square_webhook_signature_key", "sq_key")

    resp = client.post(
        "/v1/payments/webhooks/square",
        content=json.dumps({"type": "payment.completed", "data": {}}),
        headers={"x-square-hmacsha256-signature": "not-the-real-hmac"},
    )

    assert resp.status_code == 401


def test_square_webhook_accepts_a_correctly_signed_body(client, monkeypatch) -> None:
    """Positive control: the gate isn't just 'reject everything'. A body signed
    with the configured key passes verification and is processed (here it's a
    type we ignore, so nothing is captured and it 200s)."""
    key = "sq_key"
    monkeypatch.setattr(app_config.settings, "square_webhook_signature_key", key)
    body = json.dumps({"type": "payment.updated", "data": {}}).encode()
    sig = base64.b64encode(hmac.new(key.encode(), body, hashlib.sha256).digest()).decode()

    resp = client.post(
        "/v1/payments/webhooks/square",
        content=body,
        headers={"x-square-hmacsha256-signature": sig},
    )

    assert resp.status_code == 200
