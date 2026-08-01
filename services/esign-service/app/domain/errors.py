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


class ProposalNotFoundError(Exception):
    """No such proposal, or it belongs to another tenant.

    Deliberately one error for both cases — proposal-service returns 404 for a
    proposal outside the caller's tenant, and preserving that ambiguity here
    keeps this service from confirming that another tenant's proposal exists.
    """


class ProposalNotSignableError(Exception):
    """The proposal exists but isn't in a state a customer can sign.

    A DRAFT proposal's public `/view` 404s by design, so a signer would be
    asked to adopt a legally binding signature on a document they can never
    open (T204c).
    """


class UpstreamServiceError(Exception):
    """A synchronous call to another service failed (ADR-0003).

    Carries the upstream status code when there was one, so a caller can tell
    "the proposal isn't there" apart from "proposal-service is down" — the two
    demand different HTTP responses and very different operator attention.
    """

    def __init__(self, service_name: str, detail: str, status_code: int | None = None) -> None:
        super().__init__(f"{service_name}: {detail}")
        self.service_name = service_name
        self.detail = detail
        self.status_code = status_code
