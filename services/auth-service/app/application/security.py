"""Security primitives — password hashing, JWT, MFA (TOTP), token hashing.

Pure, dependency-light, and unit-testable without a database. Password hashing
uses PBKDF2-HMAC-SHA256 (stdlib, OWASP-aligned) for portability; argon2 is the
documented production target (swap `hash_password`/`verify_password`).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
import pyotp

from app.config import settings

# ── Passwords ────────────────────────────────────────────────────────────────

_PBKDF2_ALGO = "sha256"


def hash_password(password: str, *, iterations: int | None = None) -> str:
    """Return a self-describing PHC-like string: pbkdf2$<algo>$<iters>$<salt>$<hash>."""
    if not password:
        raise ValueError("password must not be empty")
    iters = iterations or settings.pbkdf2_iterations
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, password.encode(), salt, iters)
    return f"pbkdf2${_PBKDF2_ALGO}${iters}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, algo, iters_s, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(algo, password.encode(), _unb64(salt_b64), int(iters_s))
        return hmac.compare_digest(dk, _unb64(hash_b64))
    except (ValueError, TypeError):
        return False


# ── JWT access tokens ────────────────────────────────────────────────────────


def issue_access_token(*, user_id: UUID, tenant_id: UUID, roles: list[str]) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_expires_in)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.InvalidTokenError (incl. expiry) on any problem."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# ── Refresh tokens (opaque, store only the hash) ─────────────────────────────


def new_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Give the raw to the client; store the hash."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── MFA (TOTP) ───────────────────────────────────────────────────────────────


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, *, account: str, issuer: str = "TradeQuote AI") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# ── helpers ──────────────────────────────────────────────────────────────────


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
