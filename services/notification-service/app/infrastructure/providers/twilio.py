"""Concrete SMS provider: Twilio Messages API over HTTP.

Third-party API, so `httpx` with an explicit timeout (not the internal
ServiceClient). Failures normalize to `NotificationDeliveryError`. Not exercised
by the test suite (console is the default); covered against fakes at the
use-case level.
"""

from __future__ import annotations

from uuid import uuid4

import httpx

from app.domain.errors import NotificationDeliveryError


class TwilioSmsProvider:
    name = "twilio"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._timeout = timeout_seconds

    def send_sms(self, to_phone: str, body: str) -> str:
        if not self._account_sid or not self._auth_token:
            raise NotificationDeliveryError("Twilio credentials are not configured")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        try:
            response = httpx.post(
                url,
                auth=(self._account_sid, self._auth_token),
                data={"To": to_phone, "From": self._from_number, "Body": body},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"twilio request failed: {exc}") from exc
        if not response.is_success:
            raise NotificationDeliveryError(
                f"twilio returned HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            return str(response.json()["sid"])
        except (ValueError, KeyError, TypeError):
            return f"twilio-{uuid4()}"
