"""Idempotent capture (T303b): a replayed webhook (same provider event id)
must not double-capture.

Both Stripe and Square retry delivery on anything short of a 200 response,
and a network blip can also duplicate a single delivery. These tests seed a
pending payment directly, replay the *same* signed event twice, and assert
`capture_payment` only actually runs once — the second delivery must still
200 (so the provider stops retrying) without repeating the side effect.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest

import app.config as app_config
from app.domain.models import PaymentModel, PaymentProvider, PaymentStatus, PaymentType

SQUARE_URL = "https://api.tradequote.ai/v1/payments/webhooks/square"


def _stripe_signed_request(payload: dict, secret: str) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + body
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return body, f"t={timestamp},v1={sig}"


def _square_signature(url: str, body: bytes, key: str) -> str:
    mac_input = url.encode() + body
    return base64.b64encode(hmac.new(key.encode(), mac_input, hashlib.sha256).digest()).decode()


def _seed_payment(
    api_session, tenant_id: uuid.UUID, provider: PaymentProvider, provider_payment_id: str
) -> PaymentModel:
    payment = PaymentModel(
        tenant_id=tenant_id,
        quote_id=uuid.uuid4(),
        provider=provider,
        payment_type=PaymentType.DEPOSIT,
        status=PaymentStatus.PENDING,
        amount_minor=50_000,
        currency="USD",
        provider_payment_id=provider_payment_id,
        idempotency_key=str(uuid.uuid4()),
    )
    api_session.add(payment)
    api_session.flush()
    return payment


@pytest.fixture
def capture_calls(monkeypatch: pytest.MonkeyPatch) -> list:
    """Wraps the real capture_payment to count invocations.

    Unlike test_webhook_security.py's autouse bomb, idempotency tests need
    the *first* delivery to actually capture — only the *second*, replayed
    delivery must be a no-op.
    """
    from app.application.services import capture_payment as real_capture_payment

    calls: list[tuple] = []

    def _wrapped(*args, **kwargs):
        calls.append((args, kwargs))
        return real_capture_payment(*args, **kwargs)

    monkeypatch.setattr("app.interface.routes.capture_payment", _wrapped)
    return calls


def test_stripe_replayed_event_does_not_double_capture(
    client, api_session, tenant_id, auth_header, monkeypatch, capture_calls
) -> None:
    secret = "whsec_test"
    monkeypatch.setattr(app_config.settings, "stripe_webhook_secret", secret)
    payment = _seed_payment(api_session, tenant_id, PaymentProvider.STRIPE, "cs_test_dup")

    event_payload = {
        "id": "evt_dup_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_dup", "metadata": {"tenant_id": str(tenant_id)}}},
    }
    body, sig_header = _stripe_signed_request(event_payload, secret)

    first = client.post(
        "/v1/payments/webhooks/stripe", content=body, headers={"stripe-signature": sig_header}
    )
    second = client.post(
        "/v1/payments/webhooks/stripe", content=body, headers={"stripe-signature": sig_header}
    )

    assert first.status_code == 200
    assert second.status_code == 200  # still 200 so the provider stops retrying
    assert len(capture_calls) == 1  # but only captured once

    got = client.get(f"/v1/payments/{payment.id}", headers=auth_header)
    assert got.json()["status"] == "captured"


def test_square_replayed_event_does_not_double_capture(
    client, api_session, tenant_id, auth_header, monkeypatch, capture_calls
) -> None:
    key = "sq_key"
    monkeypatch.setattr(app_config.settings, "square_webhook_signature_key", key)
    monkeypatch.setattr(app_config.settings, "square_webhook_notification_url", SQUARE_URL)
    payment = _seed_payment(api_session, tenant_id, PaymentProvider.SQUARE, "sq_pay_dup")

    body = json.dumps(
        {
            "type": "payment.completed",
            "event_id": "sq_evt_dup_1",
            "data": {
                "object": {"payment": {"id": "sq_pay_dup", "note": f"{tenant_id}|quote-note"}}
            },
        }
    ).encode()
    sig = _square_signature(SQUARE_URL, body, key)

    first = client.post(
        "/v1/payments/webhooks/square",
        content=body,
        headers={"x-square-hmacsha256-signature": sig},
    )
    second = client.post(
        "/v1/payments/webhooks/square",
        content=body,
        headers={"x-square-hmacsha256-signature": sig},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(capture_calls) == 1

    got = client.get(f"/v1/payments/{payment.id}", headers=auth_header)
    assert got.json()["status"] == "captured"


def test_stripe_events_without_an_id_still_process(
    client, api_session, tenant_id, auth_header, monkeypatch, capture_calls
) -> None:
    """An event missing an id can't be deduped, but must not be dropped —
    there's nothing to dedupe against, so it should still be processed."""
    secret = "whsec_test"
    monkeypatch.setattr(app_config.settings, "stripe_webhook_secret", secret)
    _seed_payment(api_session, tenant_id, PaymentProvider.STRIPE, "cs_test_noid")

    event_payload = {
        "object": "event",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_noid", "metadata": {"tenant_id": str(tenant_id)}}},
    }
    body, sig_header = _stripe_signed_request(event_payload, secret)

    resp = client.post(
        "/v1/payments/webhooks/stripe", content=body, headers={"stripe-signature": sig_header}
    )

    assert resp.status_code == 200
    assert len(capture_calls) == 1
