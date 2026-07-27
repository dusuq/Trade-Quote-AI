"""Concrete SQLAlchemy adapters for the domain repository ports.

These map ORM rows to domain entities at the boundary, so nothing above the
infrastructure layer ever sees a SQLAlchemy object.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import (
    AuditEvent,
    Signature,
    SignatureRequest,
    SignatureRequestStatus,
)
from app.infrastructure.models import (
    SignatureAuditEventORM,
    SignatureORM,
    SignatureRequestORM,
)


def _ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime read back from the database to aware UTC.

    SQLite (the test harness) stores no timezone, so values come back naive.
    Hash verification calls `.astimezone(UTC)`, which interprets a *naive*
    datetime as local time — that would silently produce a different digest
    than the one written and fail verification on a perfectly intact chain.
    Normalizing here means domain logic only ever sees aware UTC.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return _ensure_utc(value) if value is not None else None


def _request_to_domain(row: SignatureRequestORM) -> SignatureRequest:
    return SignatureRequest(
        id=row.id,
        tenant_id=row.tenant_id,
        proposal_id=row.proposal_id,
        signer_id=row.signer_id,
        signer_name=row.signer_name,
        signer_email=row.signer_email,
        token=row.token,
        document_sha256=row.document_sha256,
        status=row.status,
        expires_at=_ensure_utc(row.expires_at),
        created_at=_ensure_utc(row.created_at),
        updated_at=_ensure_utc(row.updated_at),
        signed_at=_optional_utc(row.signed_at),
        declined_at=_optional_utc(row.declined_at),
        voided_at=_optional_utc(row.voided_at),
    )


def _signature_to_domain(row: SignatureORM) -> Signature:
    return Signature(
        id=row.id,
        tenant_id=row.tenant_id,
        request_id=row.request_id,
        signer_id=row.signer_id,
        signer_name=row.signer_name,
        signer_email=row.signer_email,
        method=row.method,
        typed_name=row.typed_name,
        image_data=row.image_data,
        signature_hash=row.signature_hash,
        document_sha256=row.document_sha256,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        consented_to_electronic_business=row.consented_to_electronic_business,
        intent_affirmed=row.intent_affirmed,
        signed_at=_ensure_utc(row.signed_at),
    )


def _audit_to_domain(row: SignatureAuditEventORM) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        request_id=row.request_id,
        sequence=row.sequence,
        event_type=row.event_type,
        payload=dict(row.payload),
        occurred_at=_ensure_utc(row.occurred_at),
        prev_hash=row.prev_hash,
        entry_hash=row.entry_hash,
    )


class SqlAlchemySignatureRequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, request: SignatureRequest) -> SignatureRequest:
        row = SignatureRequestORM(
            id=request.id,
            tenant_id=request.tenant_id,
            proposal_id=request.proposal_id,
            signer_id=request.signer_id,
            signer_name=request.signer_name,
            signer_email=request.signer_email,
            token=request.token,
            document_sha256=request.document_sha256,
            status=request.status,
            expires_at=request.expires_at,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )
        self.session.add(row)
        self.session.flush()
        return _request_to_domain(row)

    def get(self, tenant_id: UUID, request_id: UUID) -> SignatureRequest | None:
        row = self.session.scalar(
            select(SignatureRequestORM).where(
                SignatureRequestORM.id == request_id,
                SignatureRequestORM.tenant_id == tenant_id,
            )
        )
        return _request_to_domain(row) if row else None

    def get_by_token(self, tenant_id: UUID, token: str) -> SignatureRequest | None:
        row = self.session.scalar(
            select(SignatureRequestORM).where(
                SignatureRequestORM.token == token,
                SignatureRequestORM.tenant_id == tenant_id,
            )
        )
        return _request_to_domain(row) if row else None

    def list_for_tenant(
        self,
        tenant_id: UUID,
        proposal_id: UUID | None = None,
        status: SignatureRequestStatus | None = None,
    ) -> list[SignatureRequest]:
        stmt = select(SignatureRequestORM).where(SignatureRequestORM.tenant_id == tenant_id)
        if proposal_id is not None:
            stmt = stmt.where(SignatureRequestORM.proposal_id == proposal_id)

        # EXPIRED is a *computed* status (see application.effective_status) —
        # nothing writes it. Filtering has to mirror that computation, or
        # ?status=pending would hand back links that have already lapsed.
        now = datetime.now(UTC)
        if status is SignatureRequestStatus.EXPIRED:
            stmt = stmt.where(
                SignatureRequestORM.status == SignatureRequestStatus.PENDING,
                SignatureRequestORM.expires_at <= now,
            )
        elif status is SignatureRequestStatus.PENDING:
            stmt = stmt.where(
                SignatureRequestORM.status == SignatureRequestStatus.PENDING,
                SignatureRequestORM.expires_at > now,
            )
        elif status is not None:
            stmt = stmt.where(SignatureRequestORM.status == status)

        stmt = stmt.order_by(SignatureRequestORM.created_at.desc())
        return [_request_to_domain(row) for row in self.session.scalars(stmt).all()]

    def update(self, request: SignatureRequest) -> SignatureRequest:
        row = self.session.scalar(
            select(SignatureRequestORM).where(
                SignatureRequestORM.id == request.id,
                SignatureRequestORM.tenant_id == request.tenant_id,
            )
        )
        if row is None:
            raise LookupError(f"Signature request '{request.id}' not found for update.")
        row.status = request.status
        row.signed_at = request.signed_at
        row.declined_at = request.declined_at
        row.voided_at = request.voided_at
        row.updated_at = request.updated_at
        self.session.flush()
        return _request_to_domain(row)


class SqlAlchemySignatureRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, signature: Signature) -> Signature:
        row = SignatureORM(
            id=signature.id,
            tenant_id=signature.tenant_id,
            request_id=signature.request_id,
            signer_id=signature.signer_id,
            signer_name=signature.signer_name,
            signer_email=signature.signer_email,
            method=signature.method,
            typed_name=signature.typed_name,
            image_data=signature.image_data,
            signature_hash=signature.signature_hash,
            document_sha256=signature.document_sha256,
            ip_address=signature.ip_address,
            user_agent=signature.user_agent,
            consented_to_electronic_business=signature.consented_to_electronic_business,
            intent_affirmed=signature.intent_affirmed,
            signed_at=signature.signed_at,
        )
        self.session.add(row)
        self.session.flush()
        return _signature_to_domain(row)

    def get_for_request(self, tenant_id: UUID, request_id: UUID) -> Signature | None:
        row = self.session.scalar(
            select(SignatureORM).where(
                SignatureORM.request_id == request_id,
                SignatureORM.tenant_id == tenant_id,
            )
        )
        return _signature_to_domain(row) if row else None


class SqlAlchemyAuditTrailRepository:
    """Append + read only. No update or delete method exists on this class by
    design — an audit chain you can edit through the ORM isn't evidence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: AuditEvent) -> AuditEvent:
        row = SignatureAuditEventORM(
            id=event.id,
            tenant_id=event.tenant_id,
            request_id=event.request_id,
            sequence=event.sequence,
            event_type=event.event_type,
            payload=event.payload,
            occurred_at=event.occurred_at,
            prev_hash=event.prev_hash,
            entry_hash=event.entry_hash,
        )
        self.session.add(row)
        self.session.flush()
        return _audit_to_domain(row)

    def list_for_request(self, tenant_id: UUID, request_id: UUID) -> list[AuditEvent]:
        stmt = (
            select(SignatureAuditEventORM)
            .where(
                SignatureAuditEventORM.request_id == request_id,
                SignatureAuditEventORM.tenant_id == tenant_id,
            )
            .order_by(SignatureAuditEventORM.sequence)
        )
        return [_audit_to_domain(row) for row in self.session.scalars(stmt).all()]

    def last_entry(self, tenant_id: UUID, request_id: UUID) -> AuditEvent | None:
        row = self.session.scalar(
            select(SignatureAuditEventORM)
            .where(
                SignatureAuditEventORM.request_id == request_id,
                SignatureAuditEventORM.tenant_id == tenant_id,
            )
            .order_by(SignatureAuditEventORM.sequence.desc())
            .limit(1)
        )
        return _audit_to_domain(row) if row else None
