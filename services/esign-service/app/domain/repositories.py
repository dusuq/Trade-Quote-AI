"""Repository protocols (ports).

The application layer depends only on these — never on SQLAlchemy — so every
use case is unit-testable against plain in-memory fakes with no database
(conventions §3; customer-service is the reference).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.entities import (
    AuditEvent,
    Signature,
    SignatureRequest,
    SignatureRequestStatus,
)


class SignatureRequestRepository(Protocol):
    def add(self, request: SignatureRequest) -> SignatureRequest: ...
    def get(self, tenant_id: UUID, request_id: UUID) -> SignatureRequest | None: ...
    def get_by_token(self, tenant_id: UUID, token: str) -> SignatureRequest | None: ...
    def list_for_tenant(
        self,
        tenant_id: UUID,
        proposal_id: UUID | None = None,
        status: SignatureRequestStatus | None = None,
    ) -> list[SignatureRequest]: ...
    def update(self, request: SignatureRequest) -> SignatureRequest: ...


class SignatureRepository(Protocol):
    def add(self, signature: Signature) -> Signature: ...
    def get_for_request(self, tenant_id: UUID, request_id: UUID) -> Signature | None: ...


class AuditTrailRepository(Protocol):
    def append(self, event: AuditEvent) -> AuditEvent: ...
    def list_for_request(self, tenant_id: UUID, request_id: UUID) -> list[AuditEvent]: ...
    def last_entry(self, tenant_id: UUID, request_id: UUID) -> AuditEvent | None: ...


class TenantResolver(Protocol):
    def resolve_by_token(self, token: str) -> UUID | None:
        """Return the tenant owning `token`, or None.

        Used only by the public `/v1/sign/*` routes, which arrive with no
        tenant context at all — there is no header or session to open a
        tenant-scoped session from. Mirrors proposal-service's TenantResolver.
        """
        ...
