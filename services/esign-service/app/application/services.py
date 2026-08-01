"""Use cases for E-Signature (M10 / T204).

Every function here depends only on repository Protocols, so the whole layer
is exercisable against in-memory fakes with no database (conventions §3).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.domain.entities import (
    AuditEvent,
    AuditEventType,
    Signature,
    SignatureMethod,
    SignatureRequest,
    SignatureRequestStatus,
)
from app.domain.errors import (
    ConsentNotGivenError,
    DocumentMismatchError,
    ProposalNotFoundError,
    ProposalNotSignableError,
    SignatureRequestNotFoundError,
    SignatureRequestNotOpenError,
)
from app.domain.events import DomainEvent, document_signed
from app.domain.hash_chain import (
    GENESIS_HASH,
    SEQUENCE_START,
    ChainVerification,
    compute_entry_hash,
    compute_signature_hash,
    verify_chain,
)
from app.domain.repositories import (
    AuditTrailRepository,
    ProposalReader,
    SignatureRepository,
    SignatureRequestRepository,
)

DEFAULT_EXPIRY_DAYS = 30

# Proposal statuses a customer can be asked to sign. DRAFT is excluded because
# its public `/view` 404s by design — the signer could never open the document
# they'd be adopting a legally binding signature on. Mirrors proposal-service's
# ProposalStatus (draft | sent | viewed).
SIGNABLE_PROPOSAL_STATUSES = frozenset({"sent", "viewed"})

# 32 bytes -> ~256 bits of entropy, URL-safe. The signing link is the only
# thing standing between the public internet and a legally binding act
# (design spec D2), so this is deliberately far beyond guessing range.
TOKEN_BYTES = 32


def utcnow() -> datetime:
    return datetime.now(UTC)


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def effective_status(request: SignatureRequest, now: datetime) -> SignatureRequestStatus:
    """Status as the world should see it.

    A PENDING request past its expiry reports EXPIRED without anything having
    written that to the database — so correctness doesn't depend on a sweeper
    job having run recently.
    """
    if request.status == SignatureRequestStatus.PENDING and request.is_expired(now):
        return SignatureRequestStatus.EXPIRED
    return request.status


def append_audit_entry(
    audit: AuditTrailRepository,
    *,
    tenant_id: UUID,
    request_id: UUID,
    event_type: AuditEventType,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> AuditEvent:
    """Append one link, chained to whatever is currently last.

    Reading the tail inside this function (rather than taking it as an
    argument) keeps every caller on the same path and makes it impossible to
    append a link that doesn't reference the true previous hash.
    """
    last = audit.last_entry(tenant_id, request_id)
    sequence = last.sequence + 1 if last else SEQUENCE_START
    prev_hash = last.entry_hash if last else GENESIS_HASH

    entry_hash = compute_entry_hash(
        request_id=request_id,
        sequence=sequence,
        event_type=event_type.value,
        payload=payload,
        occurred_at=occurred_at,
        prev_hash=prev_hash,
    )

    return audit.append(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            request_id=request_id,
            sequence=sequence,
            event_type=event_type.value,
            payload=payload,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
    )


def assert_proposal_signable(
    proposals: ProposalReader,
    *,
    tenant_id: UUID,
    proposal_id: UUID,
) -> str:
    """Confirm the proposal exists in this tenant and can actually be signed.

    Until T204c this service accepted `proposal_id` entirely on the client's
    word — it never contacted proposal-service at all — so the hash-chained,
    legally-framed audit trail could be bound to a proposal reference nothing
    had validated.

    **Performs network I/O.** Callers must invoke this *before* opening a
    database transaction, never inside one (ADR-0003 rule 3).
    """
    status = proposals.get_status(tenant_id, proposal_id)
    if status is None:
        raise ProposalNotFoundError(f"proposal {proposal_id} not found")
    if status not in SIGNABLE_PROPOSAL_STATUSES:
        raise ProposalNotSignableError(
            f"proposal is '{status}' — send it to the customer before requesting a signature"
        )
    return status


def create_signature_request(
    requests: SignatureRequestRepository,
    audit: AuditTrailRepository,
    *,
    tenant_id: UUID,
    proposal_id: UUID,
    signer_name: str,
    signer_email: str,
    document_sha256: str,
    expires_in_days: int = DEFAULT_EXPIRY_DAYS,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> SignatureRequest:
    now = now or utcnow()
    request = SignatureRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        proposal_id=proposal_id,
        signer_id=uuid4(),
        signer_name=signer_name,
        signer_email=signer_email,
        token=generate_token(),
        document_sha256=document_sha256,
        status=SignatureRequestStatus.PENDING,
        expires_at=now + timedelta(days=expires_in_days),
        created_at=now,
        updated_at=now,
    )
    stored = requests.add(request)

    append_audit_entry(
        audit,
        tenant_id=tenant_id,
        request_id=stored.id,
        event_type=AuditEventType.REQUEST_CREATED,
        payload={
            "proposal_id": str(proposal_id),
            "signer_id": str(stored.signer_id),
            "signer_email": signer_email,
            "document_sha256": document_sha256,
            "expires_at": stored.expires_at.astimezone(UTC).isoformat(),
            "actor_id": str(actor_id) if actor_id else None,
        },
        occurred_at=now,
    )
    return stored


def get_signature_request(
    requests: SignatureRequestRepository, tenant_id: UUID, request_id: UUID
) -> SignatureRequest:
    request = requests.get(tenant_id, request_id)
    if request is None:
        raise SignatureRequestNotFoundError(f"Signature request '{request_id}' not found.")
    return request


def list_signature_requests(
    requests: SignatureRequestRepository,
    tenant_id: UUID,
    proposal_id: UUID | None = None,
    status: SignatureRequestStatus | None = None,
) -> list[SignatureRequest]:
    return requests.list_for_tenant(tenant_id, proposal_id=proposal_id, status=status)


def _require_request_by_token(
    requests: SignatureRequestRepository, tenant_id: UUID, token: str
) -> SignatureRequest:
    request = requests.get_by_token(tenant_id, token)
    if request is None:
        raise SignatureRequestNotFoundError("No signature request for that link.")
    return request


def record_document_opened(
    requests: SignatureRequestRepository,
    audit: AuditTrailRepository,
    *,
    tenant_id: UUID,
    token: str,
    ip_address: str,
    user_agent: str | None,
    now: datetime | None = None,
) -> SignatureRequest:
    """Public. Fetch what's being signed and log that the signer opened it.

    A closed request (signed/declined/voided/expired) is still returned so
    the signer sees a meaningful status page, but generates no audit entry —
    the chain records acts, not re-reads of a finished document.
    """
    now = now or utcnow()
    request = _require_request_by_token(requests, tenant_id, token)

    if request.is_open(now):
        append_audit_entry(
            audit,
            tenant_id=tenant_id,
            request_id=request.id,
            event_type=AuditEventType.DOCUMENT_OPENED,
            payload={"ip_address": ip_address, "user_agent": user_agent},
            occurred_at=now,
        )
    return request


def apply_signature(
    requests: SignatureRequestRepository,
    signatures: SignatureRepository,
    audit: AuditTrailRepository,
    *,
    tenant_id: UUID,
    token: str,
    method: SignatureMethod,
    typed_name: str | None,
    image_data: str | None,
    document_sha256: str,
    ip_address: str,
    user_agent: str | None,
    consented_to_electronic_business: bool,
    intent_affirmed: bool,
    now: datetime | None = None,
) -> tuple[Signature, SignatureRequest, DomainEvent]:
    """Public. Capture the signature and close the request.

    Validation order is deliberate: integrity of *what* is being signed is
    checked before intent, because consent given against a different document
    is not consent to this one.
    """
    now = now or utcnow()
    request = _require_request_by_token(requests, tenant_id, token)

    if not request.is_open(now):
        raise SignatureRequestNotOpenError(
            f"This signature request is {effective_status(request, now).value}."
        )

    if document_sha256 != request.document_sha256:
        raise DocumentMismatchError(
            "The document being signed does not match the one this request was created for."
        )

    if not consented_to_electronic_business or not intent_affirmed:
        raise ConsentNotGivenError(
            "Both consent to transact electronically and intent to sign are required."
        )

    signature_hash = compute_signature_hash(
        signer_id=request.signer_id,
        signer_name=request.signer_name,
        document_sha256=document_sha256,
        ip_address=ip_address,
        signed_at=now,
    )

    signature = signatures.add(
        Signature(
            id=uuid4(),
            tenant_id=tenant_id,
            request_id=request.id,
            signer_id=request.signer_id,
            signer_name=request.signer_name,
            signer_email=request.signer_email,
            method=method,
            typed_name=typed_name,
            image_data=image_data,
            signature_hash=signature_hash,
            document_sha256=document_sha256,
            ip_address=ip_address,
            user_agent=user_agent,
            consented_to_electronic_business=consented_to_electronic_business,
            intent_affirmed=intent_affirmed,
            signed_at=now,
        )
    )

    request.status = SignatureRequestStatus.SIGNED
    request.signed_at = now
    request.updated_at = now
    requests.update(request)

    append_audit_entry(
        audit,
        tenant_id=tenant_id,
        request_id=request.id,
        event_type=AuditEventType.SIGNATURE_APPLIED,
        payload={
            "signature_id": str(signature.id),
            "signer_id": str(request.signer_id),
            "method": method.value,
            "signature_hash": signature_hash,
            "document_sha256": document_sha256,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "consented_to_electronic_business": consented_to_electronic_business,
            "intent_affirmed": intent_affirmed,
        },
        occurred_at=now,
    )

    event = document_signed(
        tenant_id,
        proposal_id=request.proposal_id,
        signer_id=request.signer_id,
        signature_hash=signature_hash,
        ip_address=ip_address,
        signed_at=now,
    )
    return signature, request, event


def decline_signature(
    requests: SignatureRequestRepository,
    audit: AuditTrailRepository,
    *,
    tenant_id: UUID,
    token: str,
    reason: str | None,
    ip_address: str,
    user_agent: str | None,
    now: datetime | None = None,
) -> SignatureRequest:
    """Public. The signer refuses. Terminal, and recorded in the chain."""
    now = now or utcnow()
    request = _require_request_by_token(requests, tenant_id, token)

    if not request.is_open(now):
        raise SignatureRequestNotOpenError(
            f"This signature request is {effective_status(request, now).value}."
        )

    request.status = SignatureRequestStatus.DECLINED
    request.declined_at = now
    request.updated_at = now
    requests.update(request)

    append_audit_entry(
        audit,
        tenant_id=tenant_id,
        request_id=request.id,
        event_type=AuditEventType.REQUEST_DECLINED,
        payload={"reason": reason, "ip_address": ip_address, "user_agent": user_agent},
        occurred_at=now,
    )
    return request


def void_signature_request(
    requests: SignatureRequestRepository,
    audit: AuditTrailRepository,
    *,
    tenant_id: UUID,
    request_id: UUID,
    actor_id: UUID | None,
    reason: str | None = None,
    now: datetime | None = None,
) -> SignatureRequest:
    """Authenticated. The contractor withdraws the request; the link dies."""
    now = now or utcnow()
    request = get_signature_request(requests, tenant_id, request_id)

    if request.status != SignatureRequestStatus.PENDING:
        raise SignatureRequestNotOpenError(
            f"Only a pending request can be voided; this one is {request.status.value}."
        )

    request.status = SignatureRequestStatus.VOIDED
    request.voided_at = now
    request.updated_at = now
    requests.update(request)

    append_audit_entry(
        audit,
        tenant_id=tenant_id,
        request_id=request.id,
        event_type=AuditEventType.REQUEST_VOIDED,
        payload={"actor_id": str(actor_id) if actor_id else None, "reason": reason},
        occurred_at=now,
    )
    return request


def get_audit_trail(
    requests: SignatureRequestRepository,
    audit: AuditTrailRepository,
    tenant_id: UUID,
    request_id: UUID,
) -> tuple[list[AuditEvent], ChainVerification]:
    """The chain plus a *freshly computed* verification of it.

    Verification is recomputed on every read rather than cached, so the
    answer reflects the data as it exists right now — a cached "valid" flag
    would be exactly the thing an attacker edits.
    """
    get_signature_request(requests, tenant_id, request_id)
    entries = audit.list_for_request(tenant_id, request_id)
    return entries, verify_chain(entries)


def get_signature(
    signatures: SignatureRepository, tenant_id: UUID, request_id: UUID
) -> Signature | None:
    return signatures.get_for_request(tenant_id, request_id)
