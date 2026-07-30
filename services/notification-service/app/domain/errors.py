"""Domain errors. The interface layer maps these to HTTP status codes."""

from __future__ import annotations


class UnsupportedChannelError(Exception):
    """The requested channel has no delivery adapter (→ 422).

    E.g. 'whatsapp'/'push' are valid enum values and DB-storable, but this
    service can only deliver email and SMS today.
    """


class InvalidRecipientError(Exception):
    """The recipient doesn't look valid for its channel (→ 422)."""


class TemplateNotFoundError(Exception):
    """No custom template and no built-in default for (name, channel) (→ 404)."""


class NotificationNotFoundError(Exception):
    """The requested notification doesn't exist for this tenant (→ 404)."""


class NotificationDeliveryError(Exception):
    """A provider (SendGrid/Resend/Twilio) rejected or failed the send.

    Raised inside the background delivery task; it never reaches the client
    (the send endpoint has already returned 202). It is caught by the use case,
    which records `status='failed'` and the message on the ledger row.
    """
