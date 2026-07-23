"""Unit tests for the security primitives — no database required."""

from __future__ import annotations

import uuid

import jwt
import pytest

from app.application import security


def test_password_hash_roundtrip() -> None:
    hashed = security.hash_password("correct horse battery staple", iterations=50_000)
    assert hashed.startswith("pbkdf2$sha256$")
    assert security.verify_password("correct horse battery staple", hashed)
    assert not security.verify_password("wrong password", hashed)


def test_password_hash_is_salted() -> None:
    a = security.hash_password("same", iterations=50_000)
    b = security.hash_password("same", iterations=50_000)
    assert a != b  # random salt → different encodings
    assert security.verify_password("same", a)
    assert security.verify_password("same", b)


def test_empty_password_rejected() -> None:
    with pytest.raises(ValueError):
        security.hash_password("")


def test_verify_password_handles_garbage() -> None:
    assert not security.verify_password("x", "not-a-valid-hash")


def test_access_token_roundtrip() -> None:
    uid, tid = uuid.uuid4(), uuid.uuid4()
    token = security.issue_access_token(user_id=uid, tenant_id=tid, roles=["owner", "admin"])
    claims = security.decode_access_token(token)
    assert claims["sub"] == str(uid)
    assert claims["tid"] == str(tid)
    assert claims["roles"] == ["owner", "admin"]
    assert claims["typ"] == "access"


def test_expired_token_rejected() -> None:
    from app.config import settings

    original = settings.jwt_expires_in
    settings.jwt_expires_in = -10  # already expired
    try:
        token = security.issue_access_token(
            user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=[]
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            security.decode_access_token(token)
    finally:
        settings.jwt_expires_in = original


def test_refresh_token_hashing() -> None:
    raw, hashed = security.new_refresh_token()
    assert raw and hashed
    assert security.hash_token(raw) == hashed
    assert hashed != raw


def test_totp_verify() -> None:
    import pyotp

    secret = security.new_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert security.verify_totp(secret, code)
    assert not security.verify_totp(secret, "000000")


def test_totp_provisioning_uri() -> None:
    uri = security.totp_provisioning_uri(security.new_totp_secret(), account="a@b.com")
    assert uri.startswith("otpauth://totp/")
    assert "TradeQuote%20AI" in uri or "TradeQuote AI" in uri
