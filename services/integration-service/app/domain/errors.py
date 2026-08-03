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


class TokenEncryptionError(Exception):
    """A stored token failed to decrypt/authenticate.

    Raised by `TokenCipher.decrypt` when the ciphertext is malformed or was
    encrypted under a different key (e.g. `INTEGRATION_TOKEN_ENCRYPTION_KEY`
    rotated without re-encrypting existing rows). Never wraps the ciphertext
    or plaintext in the message — see app/infrastructure/crypto.py.
    """


class OAuthStateInvalidError(Exception):
    """The OAuth `state` on a provider callback is malformed or doesn't match
    the nonce recorded when the flow started. Mapped to a generic 400 by the
    public callback route — never confirms or denies which part was wrong."""
