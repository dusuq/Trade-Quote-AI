"""HTTP routes for E-Signature.

Two routers with deliberately different trust models:

* `/v1/signature-requests` — contractor side. Trusts the gateway's
  `x-tenant-id` header (conventions §1).
* `/v1/sign` — **public and unauthenticated**. A customer signing a quote has
  no TradeQuote account, so there is no token, no session, and no tenant
  header. Tenant is resolved from the signing token via a SECURITY DEFINER
  function. This is the second such route in the codebase, after
  proposal-service's `/v1/proposals/{id}/view`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.application import services
from app.config import settings
from app.domain.entities import SignatureRequest, SignatureRequestStatus
from app.domain.errors import (
    ConsentNotGivenError,
    DocumentMismatchError,
    ProposalNotFoundError,
    ProposalNotSignableError,
    SignatureRequestNotFoundError,
    SignatureRequestNotOpenError,
    UpstreamServiceError,
)
from app.domain.repositories import ProposalReader, TenantResolver
from app.infrastructure.db import PostgresTenantResolver, tenant_session
from app.infrastructure.http import ServiceClient
from app.infrastructure.proposal_reader import HttpProposalReader
from app.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyAuditTrailRepository,
    SqlAlchemySignatureRepository,
    SqlAlchemySignatureRequestRepository,
)
from app.interface.schemas import (
    ApplySignature,
    AuditEntryResponse,
    AuditTrailResponse,
    ChainVerificationResponse,
    DeclineSignature,
    PublicSigningContext,
    SignatureRequestCreate,
    SignatureRequestDetail,
    SignatureRequestSummary,
    SignatureResponse,
    VoidSignatureRequest,
)

router = APIRouter(prefix="/v1/signature-requests", tags=["signature-requests"])
public_router = APIRouter(prefix="/v1/sign", tags=["public-signing"])

_tenant_resolver: TenantResolver = PostgresTenantResolver()

# One pooled client for proposal-service. Constructing `httpx.Client` opens no
# connection, so this is safe at import; tests swap the whole reader out on
# this attribute, the same seam `_tenant_resolver` uses.
_proposal_reader: ProposalReader = HttpProposalReader(
    ServiceClient(
        service_name="proposal-service",
        base_url=settings.proposal_service_url,
        timeout_seconds=settings.upstream_timeout_seconds,
        max_attempts=settings.upstream_max_attempts,
    )
)


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _optional_actor(x_user_id: str | None) -> uuid.UUID | None:
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return None


def _client_ip(request: Request) -> str:
    """The signer's IP, for the audit record.

    The gateway overwrites `x-forwarded-for` with the real peer address on
    every proxied request (see apps/api-gateway/src/plugins/proxy.ts), so a
    client cannot forge this by sending its own header. Falls back to the
    direct peer when the service is called without the gateway in front.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _resolve_public_tenant(token: str) -> uuid.UUID:
    tenant_id = _tenant_resolver.resolve_by_token(token)
    if tenant_id is None:
        # Same response as a token that exists but belongs elsewhere — never
        # confirm or deny that a given signing link is real.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "signing link not found")
    return tenant_id


def _to_summary(request_obj: SignatureRequest, now: datetime) -> SignatureRequestSummary:
    return SignatureRequestSummary(
        id=request_obj.id,
        proposal_id=request_obj.proposal_id,
        signer_id=request_obj.signer_id,
        signer_name=request_obj.signer_name,
        signer_email=request_obj.signer_email,
        document_sha256=request_obj.document_sha256,
        status=services.effective_status(request_obj, now),
        expires_at=request_obj.expires_at,
        created_at=request_obj.created_at,
        signed_at=request_obj.signed_at,
        declined_at=request_obj.declined_at,
        voided_at=request_obj.voided_at,
    )


# ─────────────────────────── contractor side ───────────────────────────


@router.post("", response_model=SignatureRequestDetail, status_code=status.HTTP_201_CREATED)
def create_signature_request(
    body: SignatureRequestCreate,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> SignatureRequestDetail:
    tenant_id = _require_tenant(x_tenant_id)

    # Validate the proposal *before* opening a transaction: this is network
    # I/O, and ADR-0003 rule 3 forbids holding a pooled connection across it.
    try:
        services.assert_proposal_signable(
            _proposal_reader, tenant_id=tenant_id, proposal_id=body.proposal_id
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ProposalNotSignableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except UpstreamServiceError as exc:
        # Fail closed. We cannot confirm the document exists, so we will not
        # start a legal audit trail against it.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    with tenant_session(tenant_id) as session:
        created = services.create_signature_request(
            SqlAlchemySignatureRequestRepository(session),
            SqlAlchemyAuditTrailRepository(session),
            tenant_id=tenant_id,
            proposal_id=body.proposal_id,
            signer_name=body.signer_name,
            signer_email=body.signer_email,
            document_sha256=body.document_sha256,
            expires_in_days=body.expires_in_days,
            actor_id=_optional_actor(x_user_id),
        )
        now = services.utcnow()
        return SignatureRequestDetail(
            **_to_summary(created, now).model_dump(),
            token=created.token,
            signing_path=f"/v1/sign/{created.token}",
            signature=None,
        )


@router.get("", response_model=list[SignatureRequestSummary])
def list_signature_requests(
    proposal_id: uuid.UUID | None = Query(default=None),
    request_status: SignatureRequestStatus | None = Query(default=None, alias="status"),
    x_tenant_id: str | None = Header(default=None),
) -> list[SignatureRequestSummary]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        found = services.list_signature_requests(
            SqlAlchemySignatureRequestRepository(session),
            tenant_id,
            proposal_id=proposal_id,
            status=request_status,
        )
        now = services.utcnow()
        return [_to_summary(item, now) for item in found]


@router.get("/{request_id}", response_model=SignatureRequestDetail)
def get_signature_request(
    request_id: uuid.UUID, x_tenant_id: str | None = Header(default=None)
) -> SignatureRequestDetail:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        try:
            found = services.get_signature_request(
                SqlAlchemySignatureRequestRepository(session), tenant_id, request_id
            )
        except SignatureRequestNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

        signature = services.get_signature(
            SqlAlchemySignatureRepository(session), tenant_id, request_id
        )
        now = services.utcnow()
        return SignatureRequestDetail(
            **_to_summary(found, now).model_dump(),
            token=found.token,
            signing_path=f"/v1/sign/{found.token}",
            signature=SignatureResponse.model_validate(signature, from_attributes=True)
            if signature
            else None,
        )


@router.get("/{request_id}/audit", response_model=AuditTrailResponse)
def get_audit_trail(
    request_id: uuid.UUID, x_tenant_id: str | None = Header(default=None)
) -> AuditTrailResponse:
    """The hash chain plus a freshly recomputed verification of it."""
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        try:
            entries, verification = services.get_audit_trail(
                SqlAlchemySignatureRequestRepository(session),
                SqlAlchemyAuditTrailRepository(session),
                tenant_id,
                request_id,
            )
        except SignatureRequestNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

        return AuditTrailResponse(
            request_id=request_id,
            entries=[
                AuditEntryResponse(
                    sequence=e.sequence,
                    event_type=e.event_type,
                    payload=e.payload,
                    occurred_at=e.occurred_at,
                    prev_hash=e.prev_hash,
                    entry_hash=e.entry_hash,
                )
                for e in entries
            ],
            verification=ChainVerificationResponse(
                is_valid=verification.is_valid,
                entry_count=verification.entry_count,
                broken_at_sequence=verification.broken_at_sequence,
                reason=verification.reason,
            ),
        )


@router.post("/{request_id}/void", response_model=SignatureRequestSummary)
def void_signature_request(
    request_id: uuid.UUID,
    body: VoidSignatureRequest | None = None,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> SignatureRequestSummary:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        try:
            voided = services.void_signature_request(
                SqlAlchemySignatureRequestRepository(session),
                SqlAlchemyAuditTrailRepository(session),
                tenant_id=tenant_id,
                request_id=request_id,
                actor_id=_optional_actor(x_user_id),
                reason=body.reason if body else None,
            )
        except SignatureRequestNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except SignatureRequestNotOpenError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return _to_summary(voided, services.utcnow())


# ──────────────────────── public (unauthenticated) ────────────────────────


@public_router.get("/{token}", response_model=PublicSigningContext)
def get_signing_context(token: str, request: Request) -> PublicSigningContext:
    """What am I being asked to sign? Records that the signer opened it."""
    tenant_id = _resolve_public_tenant(token)
    with tenant_session(tenant_id) as session:
        try:
            found = services.record_document_opened(
                SqlAlchemySignatureRequestRepository(session),
                SqlAlchemyAuditTrailRepository(session),
                tenant_id=tenant_id,
                token=token,
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except SignatureRequestNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "signing link not found") from exc

        now = services.utcnow()
        return PublicSigningContext(
            proposal_id=found.proposal_id,
            signer_name=found.signer_name,
            document_sha256=found.document_sha256,
            status=services.effective_status(found, now),
            expires_at=found.expires_at,
            can_sign=found.is_open(now),
        )


@public_router.post("/{token}", response_model=SignatureResponse, status_code=status.HTTP_201_CREATED)
def apply_signature(token: str, body: ApplySignature, request: Request) -> SignatureResponse:
    tenant_id = _resolve_public_tenant(token)
    with tenant_session(tenant_id) as session:
        try:
            signature, _req, _event = services.apply_signature(
                SqlAlchemySignatureRequestRepository(session),
                SqlAlchemySignatureRepository(session),
                SqlAlchemyAuditTrailRepository(session),
                tenant_id=tenant_id,
                token=token,
                method=body.method,
                typed_name=body.typed_name,
                image_data=body.image_data,
                document_sha256=body.document_sha256,
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                consented_to_electronic_business=body.consented_to_electronic_business,
                intent_affirmed=body.intent_affirmed,
            )
            # TODO(outbox): persist _event once a transactional outbox exists
            # (same TODO already carried by proposal-service's routes).
        except SignatureRequestNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "signing link not found") from exc
        except SignatureRequestNotOpenError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except DocumentMismatchError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ConsentNotGivenError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

        return SignatureResponse.model_validate(signature, from_attributes=True)


@public_router.post("/{token}/decline", response_model=PublicSigningContext)
def decline_signature(
    token: str, request: Request, body: DeclineSignature | None = None
) -> PublicSigningContext:
    tenant_id = _resolve_public_tenant(token)
    with tenant_session(tenant_id) as session:
        try:
            declined = services.decline_signature(
                SqlAlchemySignatureRequestRepository(session),
                SqlAlchemyAuditTrailRepository(session),
                tenant_id=tenant_id,
                token=token,
                reason=body.reason if body else None,
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except SignatureRequestNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "signing link not found") from exc
        except SignatureRequestNotOpenError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

        now = services.utcnow()
        return PublicSigningContext(
            proposal_id=declined.proposal_id,
            signer_name=declined.signer_name,
            document_sha256=declined.document_sha256,
            status=services.effective_status(declined, now),
            expires_at=declined.expires_at,
            can_sign=False,
        )
