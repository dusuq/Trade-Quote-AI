"""Concrete email providers over HTTP: SendGrid and Resend.

These call third-party APIs (not internal TradeQuote services), so they use
`httpx` directly with an explicit timeout rather than the internal ADR-0003
`ServiceClient`. Any non-2xx or transport failure is normalized to
`NotificationDeliveryError` so no `httpx` exception escapes this layer.

Not exercised by the test suite (which defaults to the console provider); the
delivery contract is covered against fakes at the use-case level.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from app.domain.errors import NotificationDeliveryError


class SendGridEmailProvider:
    name = "sendgrid"

    def __init__(
        self,
        api_key: str,
        *,
        from_email: str,
        from_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name
        self._timeout = timeout_seconds

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        *,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> str:
        if not self._api_key:
            raise NotificationDeliveryError("SENDGRID_API_KEY is not configured")
        payload: dict[str, Any] = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {
                "email": from_email or self._from_email,
                "name": from_name or self._from_name,
            },
            "subject": subject,
            "content": [{"type": "text/html", "value": body}],
        }
        try:
            response = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"sendgrid request failed: {exc}") from exc
        if not response.is_success:
            raise NotificationDeliveryError(
                f"sendgrid returned HTTP {response.status_code}: {response.text[:200]}"
            )
        # SendGrid returns the id in a response header; fall back to a synthetic one.
        return response.headers.get("x-message-id") or f"sendgrid-{uuid4()}"


class ResendEmailProvider:
    name = "resend"

    def __init__(
        self,
        api_key: str,
        *,
        from_email: str,
        from_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name
        self._timeout = timeout_seconds

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        *,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> str:
        if not self._api_key:
            raise NotificationDeliveryError("RESEND_API_KEY is not configured")
        sender = from_email or self._from_email
        name = from_name or self._from_name
        payload = {
            "from": f"{name} <{sender}>",
            "to": [to_email],
            "subject": subject,
            "html": body,
        }
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"resend request failed: {exc}") from exc
        if not response.is_success:
            raise NotificationDeliveryError(
                f"resend returned HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            return str(response.json()["id"])
        except (ValueError, KeyError, TypeError):
            return f"resend-{uuid4()}"
