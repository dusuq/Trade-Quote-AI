"""SQLAlchemy ORM models for E-Signature (M10 / T204)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.entities import SignatureMethod, SignatureRequestStatus


class Base(DeclarativeBase):
    pass


# Postgres enum types declare lower-case labels (see 0008_esign.sql). Without
# values_callable SQLAlchemy persists the Python member *name* ('PENDING')
# instead of its value ('pending'), so every status filter silently matches
# nothing against a real database — invisible under SQLite, which degrades
# Enum to VARCHAR + CHECK. This is exactly the T206b bug; declared correctly
# here from the start rather than retrofitted.
def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class SignatureRequestORM(Base):
    __tablename__ = "signature_request"
    __table_args__ = (UniqueConstraint("token", name="signature_request_token_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Logical cross-context reference; the proposal lives in proposal-service,
    # so no FK (same pattern as proposal.quote_id in 0006).
    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    signer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    token: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[SignatureRequestStatus] = mapped_column(
        Enum(
            SignatureRequestStatus,
            name="signature_request_status",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SignatureRequestStatus.PENDING,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SignatureORM(Base):
    __tablename__ = "signature"
    __table_args__ = (UniqueConstraint("request_id", name="signature_request_id_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signature_request.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    method: Mapped[SignatureMethod] = mapped_column(
        Enum(
            SignatureMethod,
            name="signature_method",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    typed_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)  # fits IPv6
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    consented_to_electronic_business: Mapped[bool] = mapped_column(Boolean, nullable=False)
    intent_affirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignatureAuditEventORM(Base):
    """Append-only. Nothing in this service ever issues an UPDATE or DELETE
    against this table — that is what makes the chain meaningful."""

    __tablename__ = "signature_audit_event"
    __table_args__ = (
        UniqueConstraint("request_id", "sequence", name="signature_audit_event_request_seq_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signature_request.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
