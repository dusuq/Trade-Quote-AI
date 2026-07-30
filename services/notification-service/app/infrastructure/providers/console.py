"""Console providers — the default. Print the formatted message to the server
log and return a synthetic id, so the whole service runs and is testable with
no third-party credentials (M22 plan §Provider Strategy).

Recipients are redacted in the log line (never the plain address), matching the
redaction rule applied to events.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from app.domain.redact import redact_email, redact_phone

logger = logging.getLogger("notification.console")


class ConsoleEmailProvider:
    name = "console"

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        *,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> str:
        logger.info(
            "[EMAIL MOCK] to=%s subject=%r body=%r", redact_email(to_email), subject, body
        )
        return f"console-email-{uuid4()}"


class ConsoleSmsProvider:
    name = "console"

    def send_sms(self, to_phone: str, body: str) -> str:
        logger.info("[SMS MOCK] to=%s body=%r", redact_phone(to_phone), body)
        return f"console-sms-{uuid4()}"
