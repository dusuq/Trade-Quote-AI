"""PII redaction for recipient addresses.

Compliance rule (M22 plan §PII Redaction): recipient email addresses and phone
numbers must be redacted anywhere they leave the database — in logs and in
domain-event payloads. The plain values live only in the RLS-protected
`notification_message.recipient` column.
"""

from __future__ import annotations


def redact_email(email: str) -> str:
    """`jane@domain.com` -> `j***e@domain.com`; short locals -> `j***@domain.com`.

    Anything without an `@` is treated as opaque and redacted whole, so a
    malformed value can never slip through unredacted.
    """
    if "@" not in email:
        return redact_opaque(email)
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def redact_phone(phone: str) -> str:
    """`+14155552671` -> `+1***2671`. Anything <= 4 chars -> `****`."""
    cleaned = phone.strip()
    if len(cleaned) <= 4:
        return "****"
    return f"{cleaned[:2]}***{cleaned[-4:]}"


def redact_opaque(value: str) -> str:
    """Redact a value of unknown shape, keeping at most the first character."""
    cleaned = value.strip()
    if len(cleaned) <= 1:
        return "***"
    return f"{cleaned[0]}***"


def redact_for_channel(channel: str, recipient: str) -> str:
    """Redact `recipient` according to its channel."""
    if channel == "email":
        return redact_email(recipient)
    if channel in ("sms", "whatsapp"):
        return redact_phone(recipient)
    return redact_opaque(recipient)
