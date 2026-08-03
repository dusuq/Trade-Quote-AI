"""Domain-level errors. Interface layer maps these to HTTP status codes."""

from __future__ import annotations


class ConnectionNotFoundError(Exception):
    pass


class ConnectionAlreadyExistsError(Exception):
    pass


class ConnectionInactiveError(Exception):
    pass


class WebhookNotFoundError(Exception):
    pass


class SyncLogNotFoundError(Exception):
    pass


class ProviderAuthError(Exception):
    """OAuth exchange or refresh failed."""


class ProviderSyncError(Exception):
    """Data sync with the external provider failed."""


class InvalidWebhookPayloadError(Exception):
    pass
