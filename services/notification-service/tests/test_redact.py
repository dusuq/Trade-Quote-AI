"""PII redaction (M22 plan §PII Redaction)."""

from __future__ import annotations

from app.domain.redact import (
    redact_email,
    redact_for_channel,
    redact_opaque,
    redact_phone,
)


def test_redact_email_keeps_first_last_of_local() -> None:
    assert redact_email("jane@domain.com") == "j***e@domain.com"


def test_redact_email_short_local() -> None:
    assert redact_email("jo@domain.com") == "j***@domain.com"
    assert redact_email("a@domain.com") == "a***@domain.com"


def test_redact_email_without_at_is_opaque() -> None:
    # A malformed value must never pass through unredacted.
    assert redact_email("notanemail") == "n***"


def test_redact_phone_keeps_country_and_last_four() -> None:
    assert redact_phone("+14155552671") == "+1***2671"


def test_redact_phone_short_is_masked() -> None:
    assert redact_phone("1234") == "****"


def test_redact_opaque() -> None:
    assert redact_opaque("secret") == "s***"
    assert redact_opaque("x") == "***"


def test_redact_for_channel_dispatches() -> None:
    assert redact_for_channel("email", "jane@x.com") == "j***e@x.com"
    assert redact_for_channel("sms", "+14155552671") == "+1***2671"
    assert redact_for_channel("whatsapp", "+14155552671") == "+1***2671"
    assert redact_for_channel("push", "device-token-abc") == "d***"


def test_no_plaintext_recipient_survives_redaction() -> None:
    # Guard the invariant: the full address never appears in the redacted form.
    assert "jane" not in redact_email("jane@domain.com")
    assert "4155552671" not in redact_phone("+14155552671")
