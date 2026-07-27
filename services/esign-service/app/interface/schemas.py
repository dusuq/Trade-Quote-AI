"""Pydantic DTOs for the E-Signature HTTP surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.entities import SignatureMethod, SignatureRequestStatus

_SHA256_HEX = r"^[0-9a-fA-F]{64}$"


class SignatureRequestCreate(BaseModel):
    proposal_id: UUID
    signer_name: str = Field(min_length=1, max_length=255)
    signer_email: str = Field(min_length=3, max_length=320)
    document_sha256: str = Field(pattern=_SHA256_HEX)
    expires_in_days: int = Field(default=30, ge=1, le=365)

    @field_validator("document_sha256")
    @classmethod
    def _normalize_hash(cls, value: str) -> str:
        # Compared for equality at signing time; normalizing case here stops a
        # correct signature being rejected over nothing but hex casing.
        return value.lower()


class SignatureResponse(BaseModel):
    id: UUID
    signer_name: str
    signer_email: str
    method: SignatureMethod
    typed_name: str | None
    signature_hash: str
    document_sha256: str
    ip_address: str
    user_agent: str | None
    consented_to_electronic_business: bool
    intent_affirmed: bool
    signed_at: datetime


class SignatureRequestSummary(BaseModel):
    """List view. Deliberately omits `token` — a list endpoint should not
    spray live signing capabilities across every row."""

    id: UUID
    proposal_id: UUID
    signer_id: UUID
    signer_name: str
    signer_email: str
    document_sha256: str
    status: SignatureRequestStatus
    expires_at: datetime
    created_at: datetime
    signed_at: datetime | None
    declined_at: datetime | None
    voided_at: datetime | None


class SignatureRequestDetail(SignatureRequestSummary):
    """Single-request view (tenant-scoped). Includes the token so the
    contractor can re-send the link."""

    token: str
    signing_path: str
    signature: SignatureResponse | None = None


class ApplySignature(BaseModel):
    method: SignatureMethod = SignatureMethod.TYPED
    typed_name: str | None = Field(default=None, max_length=255)
    image_data: str | None = None
    document_sha256: str = Field(pattern=_SHA256_HEX)
    consented_to_electronic_business: bool
    intent_affirmed: bool

    @field_validator("document_sha256")
    @classmethod
    def _normalize_hash(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def _require_signature_content(self) -> Self:
        if self.method is SignatureMethod.TYPED and not (self.typed_name or "").strip():
            raise ValueError("typed_name is required when method is 'typed'")
        if self.method is SignatureMethod.DRAWN and not (self.image_data or "").strip():
            raise ValueError("image_data is required when method is 'drawn'")
        return self


class DeclineSignature(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class VoidSignatureRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class PublicSigningContext(BaseModel):
    """What an unauthenticated signer is allowed to see.

    Never carries tenant_id, the audit trail, or any internal identifier
    beyond the proposal the signer is being asked to sign.
    """

    proposal_id: UUID
    signer_name: str
    document_sha256: str
    status: SignatureRequestStatus
    expires_at: datetime
    can_sign: bool


class ChainVerificationResponse(BaseModel):
    is_valid: bool
    entry_count: int
    broken_at_sequence: int | None = None
    reason: str | None = None


class AuditEntryResponse(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    prev_hash: str
    entry_hash: str


class AuditTrailResponse(BaseModel):
    request_id: UUID
    entries: list[AuditEntryResponse]
    verification: ChainVerificationResponse
