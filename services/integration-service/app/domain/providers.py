"""Ports for external accounting-provider integrations (T308b).

Mirrors the Repository Pattern already used for persistence
(`app.domain.repositories`): the application layer depends only on these
Protocols, never on `httpx` or a concrete provider SDK, so `services.py`
stays unit-testable against in-memory fakes. Concrete implementations live in
`app.infrastructure.providers.{quickbooks,xero}` and
`app.infrastructure.crypto`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ProviderTokens:
    """Result of an OAuth exchange or refresh — always plaintext in memory,
    never persisted as-is (callers encrypt via `TokenCipher` before storage)."""

    access_token: str
    refresh_token: str | None
    expires_in: int | None  # seconds until expiry, per the provider's response
    external_account_id: str | None = None  # QBO realmId / Xero tenantId


class OAuthProvider(Protocol):
    """One implementation per OAuth2 provider (QuickBooks, Xero). Zapier has
    no OAuth flow — it is API-key/webhook based (see `services.connect_zapier`)
    — so no `OAuthProvider` exists for it."""

    def build_authorize_url(self, *, state: str) -> str: ...

    def exchange_code(self, *, code: str, callback_params: dict[str, str]) -> ProviderTokens: ...

    def refresh(self, *, refresh_token: str) -> ProviderTokens: ...


class InvoiceSyncClient(Protocol):
    """Pushes one quote/invoice to the provider's accounting API."""

    def push_invoice(
        self, *, access_token: str, external_account_id: str, payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class TokenCipher(Protocol):
    """Symmetric encryption for tokens at rest. `access_token_encrypted` /
    `refresh_token_encrypted` are guarantees, not just column names, only
    because every write path goes through `encrypt` and every read through
    `decrypt` — see app/infrastructure/crypto.py for the real implementation."""

    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...
