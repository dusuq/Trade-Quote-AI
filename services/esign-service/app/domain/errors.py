"""Domain errors. The interface layer maps these to HTTP status codes."""

from __future__ import annotations


class SignatureRequestNotFoundError(Exception):
    """No such signature request, or it belongs to another tenant."""


class SignatureRequestNotOpenError(Exception):
    """Already signed/declined/voided, or past its expiry."""


class DocumentMismatchError(Exception):
    """The document hash asserted at signing time doesn't match the one the
    request was created against — the signer is looking at a different
    document than the one on record (design spec D4)."""


class ConsentNotGivenError(Exception):
    """Intent to sign and/or consent to transact electronically was not
    affirmed. Both are prerequisites for enforceability (design spec D5)."""


class AuditChainCorruptedError(Exception):
    """The stored audit chain failed verification."""
