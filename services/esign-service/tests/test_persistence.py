"""Persistence-layer tests against the real SQLAlchemy repositories.

The fakes prove the logic; these prove the logic survives a database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Enum as SAEnum

from app.application import services
from app.domain.entities import (
    SignatureMethod,
    SignatureRequestStatus,
)
from app.domain.hash_chain import verify_chain
from app.infrastructure.models import SignatureORM, SignatureRequestORM
from app.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyAuditTrailRepository,
    SqlAlchemySignatureRepository,
    SqlAlchemySignatureRequestRepository,
)

DOCUMENT = "a" * 64
NOW = datetime(2026, 7, 28, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def repos(db_session):
    return (
        SqlAlchemySignatureRequestRepository(db_session),
        SqlAlchemySignatureRepository(db_session),
        SqlAlchemyAuditTrailRepository(db_session),
    )


def _run_full_lifecycle(repos, tenant_id: uuid.UUID):
    requests_repo, signatures_repo, audit_repo = repos
    created = services.create_signature_request(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        proposal_id=uuid.uuid4(),
        signer_name="Jordan Rivera",
        signer_email="jordan@example.com",
        document_sha256=DOCUMENT,
        now=NOW,
    )
    services.record_document_opened(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        token=created.token,
        ip_address="203.0.113.7",
        user_agent="Mozilla/5.0",
        now=NOW + timedelta(minutes=1),
    )
    services.apply_signature(
        requests_repo,
        signatures_repo,
        audit_repo,
        tenant_id=tenant_id,
        token=created.token,
        method=SignatureMethod.TYPED,
        typed_name="Jordan Rivera",
        image_data=None,
        document_sha256=DOCUMENT,
        ip_address="203.0.113.7",
        user_agent="Mozilla/5.0",
        consented_to_electronic_business=True,
        intent_affirmed=True,
        now=NOW + timedelta(minutes=5),
    )
    return created


def test_chain_still_verifies_after_a_database_round_trip(db_session, repos, tenant_id) -> None:
    """Regression guard for a subtle, silent failure mode.

    SQLite stores no timezone, so datetimes come back naive. Hash material
    calls `.astimezone(UTC)`, which reads a naive value as *local* time — so
    without normalization in the repository mapper, re-reading a perfectly
    intact chain would recompute different digests and report tampering that
    never happened. `expire_all()` forces a genuine reload rather than
    handing back the identity-mapped objects still in memory.
    """
    _requests_repo, _signatures_repo, audit_repo = repos
    created = _run_full_lifecycle(repos, tenant_id)

    db_session.expire_all()

    entries = audit_repo.list_for_request(tenant_id, created.id)
    verification = verify_chain(entries)

    assert len(entries) == 3
    assert verification.is_valid, verification.reason


def test_reloaded_request_and_signature_keep_their_values(db_session, repos, tenant_id) -> None:
    requests_repo, signatures_repo, _audit_repo = repos
    created = _run_full_lifecycle(repos, tenant_id)

    db_session.expire_all()

    reloaded = requests_repo.get(tenant_id, created.id)
    signature = signatures_repo.get_for_request(tenant_id, created.id)

    assert reloaded is not None and signature is not None
    assert reloaded.status is SignatureRequestStatus.SIGNED
    assert reloaded.expires_at.tzinfo is not None  # normalized to aware UTC
    assert signature.document_sha256 == DOCUMENT
    assert signature.method is SignatureMethod.TYPED


def test_lookup_by_token_is_tenant_scoped(db_session, repos, tenant_id, other_tenant_id) -> None:
    requests_repo, _signatures_repo, _audit_repo = repos
    created = _run_full_lifecycle(repos, tenant_id)

    assert requests_repo.get_by_token(tenant_id, created.token) is not None
    assert requests_repo.get_by_token(other_tenant_id, created.token) is None


def test_pending_filter_excludes_lapsed_requests(db_session, repos, tenant_id) -> None:
    """`EXPIRED` is computed, never written — the SQL filter has to mirror
    `effective_status` or `?status=pending` would return dead links."""
    requests_repo, _signatures_repo, audit_repo = repos
    services.create_signature_request(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        proposal_id=uuid.uuid4(),
        signer_name="Lapsed Larry",
        signer_email="larry@example.com",
        document_sha256=DOCUMENT,
        expires_in_days=1,
        now=datetime.now(UTC) - timedelta(days=10),
    )

    pending = requests_repo.list_for_tenant(tenant_id, status=SignatureRequestStatus.PENDING)
    expired = requests_repo.list_for_tenant(tenant_id, status=SignatureRequestStatus.EXPIRED)

    assert pending == []
    assert len(expired) == 1


@pytest.mark.parametrize(
    ("model", "column", "enum_cls"),
    [
        (SignatureRequestORM, "status", SignatureRequestStatus),
        (SignatureORM, "method", SignatureMethod),
    ],
)
def test_enum_columns_declare_values_callable(model, column, enum_cls) -> None:
    """T206b regression: without `values_callable`, SQLAlchemy persists the
    Python member *name* ('PENDING') against a Postgres enum declaring
    lower-case labels ('pending'), so every status filter silently matches
    nothing on a real database. Invisible under SQLite, hence this test.
    """
    column_type = model.__table__.columns[column].type

    assert isinstance(column_type, SAEnum)
    assert column_type.values_callable is not None
    values = column_type.values_callable(enum_cls)
    assert values == [member.value for member in enum_cls]
    assert all(value == value.lower() for value in values)
