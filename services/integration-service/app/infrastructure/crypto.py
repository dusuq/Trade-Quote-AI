"""Encryption for OAuth tokens at rest (T308b).

The CTO audit on T308 flagged that `access_token_encrypted` /
`refresh_token_encrypted` were column *names*, not a guarantee — nothing in
`services.py` ever encrypted anything before storing it. This module is what
closes that gap: every write to those columns goes through `encrypt()`,
every read through `decrypt()` (see `activate_connection` /
`complete_oauth_callback` / `push_invoice_sync` in `app/application/services.py`).

Fernet (AES-128-CBC + HMAC-SHA256, both authenticated — RFC 8439-style
encrypt-then-MAC) rather than a bespoke AES-GCM wrapper: it is a single,
well-reviewed primitive from `cryptography` that already handles nonce
generation, tags the ciphertext with a timestamp, and needs no manual IV
bookkeeping — a smaller surface for a service whose entire job is API
plumbing, not cryptography.

Never log the return value of `encrypt` or the input to `decrypt` — both are
sensitive (ciphertext still requires no more than the one static key to
unwrap, and ciphertext length alone can leak token length). No call site in
this service does; keep it that way.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.domain.errors import TokenEncryptionError


class FernetTokenCipher:
    """Implements `app.domain.providers.TokenCipher`."""

    def __init__(self, key: str | None = None) -> None:
        key_value = key if key is not None else settings.integration_token_encryption_key
        if not key_value:
            raise RuntimeError(
                "INTEGRATION_TOKEN_ENCRYPTION_KEY is not set — refusing to start with "
                "provider tokens stored in plaintext. Generate one with "
                "`python -c \"from cryptography.fernet import Fernet; "
                'print(Fernet.generate_key().decode())"`.'
            )
        try:
            self._fernet = Fernet(key_value.encode())
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                "INTEGRATION_TOKEN_ENCRYPTION_KEY is not a valid Fernet key "
                "(must be 32 url-safe base64-encoded bytes)."
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise TokenEncryptionError(
                "stored token failed to decrypt — wrong key, or the value predates encryption"
            ) from exc
