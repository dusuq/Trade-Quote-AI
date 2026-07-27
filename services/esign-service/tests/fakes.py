"""In-memory repository fakes.

Every use case is exercisable against these with no database at all — the
point of the Protocol ports (conventions §3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.domain.entities import (
    AuditEvent,
    Signature,
    SignatureRequest,
    SignatureRequestStatus,
)


class InMemorySignatureRequestRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, SignatureRequest] = {}

    def add(self, request: SignatureRequest) -> SignatureRequest:
        self.items[request.id] = request
        return request

    def get(self, tenant_id: UUID, request_id: UUID) -> SignatureRequest | None:
        found = self.items.get(request_id)
        return found if found and found.tenant_id == tenant_id else None

    def get_by_token(self, tenant_id: UUID, token: str) -> SignatureRequest | None:
        for item in self.items.values():
            if item.token == token and item.tenant_id == tenant_id:
                return item
        return None

    def list_for_tenant(
        self,
        tenant_id: UUID,
        proposal_id: UUID | None = None,
        status: SignatureRequestStatus | None = None,
    ) -> list[SignatureRequest]:
        now = datetime.now(UTC)
        results = [item for item in self.items.values() if item.tenant_id == tenant_id]
        if proposal_id is not None:
            results = [item for item in results if item.proposal_id == proposal_id]
        if status is SignatureRequestStatus.EXPIRED:
            results = [
                item
                for item in results
                if item.status is SignatureRequestStatus.PENDING and item.is_expired(now)
            ]
        elif status is SignatureRequestStatus.PENDING:
            results = [item for item in results if item.is_open(now)]
        elif status is not None:
            results = [item for item in results if item.status is status]
        return sorted(results, key=lambda item: item.created_at, reverse=True)

    def update(self, request: SignatureRequest) -> SignatureRequest:
        self.items[request.id] = request
        return request


class InMemorySignatureRepository:
    def __init__(self) -> None:
        self.items: list[Signature] = []

    def add(self, signature: Signature) -> Signature:
        self.items.append(signature)
        return signature

    def get_for_request(self, tenant_id: UUID, request_id: UUID) -> Signature | None:
        for item in self.items:
            if item.request_id == request_id and item.tenant_id == tenant_id:
                return item
        return None


class InMemoryAuditTrailRepository:
    def __init__(self) -> None:
        self.items: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> AuditEvent:
        self.items.append(event)
        return event

    def list_for_request(self, tenant_id: UUID, request_id: UUID) -> list[AuditEvent]:
        return sorted(
            (
                item
                for item in self.items
                if item.request_id == request_id and item.tenant_id == tenant_id
            ),
            key=lambda item: item.sequence,
        )

    def last_entry(self, tenant_id: UUID, request_id: UUID) -> AuditEvent | None:
        entries = self.list_for_request(tenant_id, request_id)
        return entries[-1] if entries else None


class FakeTenantResolver:
    """Stands in for the SECURITY DEFINER lookup, which SQLite cannot do.

    Same injectable-seam pattern proposal-service uses for
    `resolve_proposal_tenant`.
    """

    def __init__(self, tokens: dict[str, UUID] | None = None) -> None:
        self.tokens: dict[str, UUID] = tokens or {}

    def register(self, token: str, tenant_id: UUID) -> None:
        self.tokens[token] = tenant_id

    def resolve_by_token(self, token: str) -> UUID | None:
        return self.tokens.get(token)
