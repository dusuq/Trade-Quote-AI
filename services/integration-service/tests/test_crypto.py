"""Unit tests for the real Fernet-backed token cipher (T308b).

These exercise `app.infrastructure.crypto` directly — the actual
`cryptography` library, not a fake — because this is the one place in the
service where "is it really encrypted" has to be answered with more than an
assertion against a test double.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.domain.errors import TokenEncryptionError
from app.infrastructure.crypto import FernetTokenCipher


def test_round_trips_plaintext() -> None:
    cipher = FernetTokenCipher(Fernet.generate_key().decode())
    ciphertext = cipher.encrypt("super-secret-access-token")
    assert ciphertext != "super-secret-access-token"
    assert cipher.decrypt(ciphertext) == "super-secret-access-token"


def test_ciphertext_is_not_plaintext_substring() -> None:
    """Guards against a no-op "encryption" (e.g. base64) that just encodes
    the token — the ciphertext must not even contain it as a substring."""
    cipher = FernetTokenCipher(Fernet.generate_key().decode())
    token = "quickbooks-access-token-abc123"
    ciphertext = cipher.encrypt(token)
    assert token not in ciphertext


def test_same_plaintext_encrypts_differently_each_time() -> None:
    """Fernet includes a random IV — two encryptions of the same token must
    not be byte-identical, or the ciphertext itself would leak equality."""
    cipher = FernetTokenCipher(Fernet.generate_key().decode())
    a = cipher.encrypt("same-token")
    b = cipher.encrypt("same-token")
    assert a != b
    assert cipher.decrypt(a) == cipher.decrypt(b) == "same-token"


def test_decrypt_with_wrong_key_raises_token_encryption_error() -> None:
    cipher_a = FernetTokenCipher(Fernet.generate_key().decode())
    cipher_b = FernetTokenCipher(Fernet.generate_key().decode())
    ciphertext = cipher_a.encrypt("a-token")
    with pytest.raises(TokenEncryptionError):
        cipher_b.decrypt(ciphertext)


def test_decrypt_garbage_raises_token_encryption_error() -> None:
    cipher = FernetTokenCipher(Fernet.generate_key().decode())
    with pytest.raises(TokenEncryptionError):
        cipher.decrypt("not-a-real-fernet-token")


def test_missing_key_refuses_to_construct() -> None:
    with pytest.raises(RuntimeError, match="INTEGRATION_TOKEN_ENCRYPTION_KEY"):
        FernetTokenCipher("")


def test_malformed_key_refuses_to_construct() -> None:
    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        FernetTokenCipher("too-short-to-be-a-real-key")
