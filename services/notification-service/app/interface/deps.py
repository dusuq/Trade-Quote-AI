"""Composition root for provider adapters.

Providers are selected by config and hold no request state, so a single
swappable object is enough — route/background code asks `deps` for the email
and SMS providers, and tests replace `deps` with a fake that hands back
in-memory providers (no network, no credentials).

Repositories are *not* built here: they need a per-request `Session`, so the
routes construct them inline from `tenant_session`, exactly as esign-service and
proposal-service do.
"""

from __future__ import annotations

from app.config import settings
from app.domain.protocols import EmailProvider, SmsProvider
from app.infrastructure.providers.console import ConsoleEmailProvider, ConsoleSmsProvider
from app.infrastructure.providers.email_http import (
    ResendEmailProvider,
    SendGridEmailProvider,
)
from app.infrastructure.providers.twilio import TwilioSmsProvider


class Dependencies:
    def email_provider(self) -> EmailProvider:
        if settings.provider_email == "sendgrid":
            return SendGridEmailProvider(
                settings.sendgrid_api_key,
                from_email=settings.email_from_address,
                from_name=settings.email_from_name,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        if settings.provider_email == "resend":
            return ResendEmailProvider(
                settings.resend_api_key,
                from_email=settings.email_from_address,
                from_name=settings.email_from_name,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        return ConsoleEmailProvider()

    def sms_provider(self) -> SmsProvider:
        if settings.provider_sms == "twilio":
            return TwilioSmsProvider(
                settings.twilio_account_sid,
                settings.twilio_auth_token,
                settings.twilio_from_number,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        return ConsoleSmsProvider()


deps = Dependencies()
