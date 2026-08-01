"""Use-case tests. Everything here runs against in-memory fakes — no database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application import services
from app.domain.entities import SignatureMethod, SignatureRequestStatus
from app.domain.errors import (
    ConsentNotGivenError,
    DocumentMismatchError,
    ProposalNotFoundError,
    ProposalNotSignableError,
    SignatureRequestNotFoundError,
    SignatureRequestNotOpenError,
    UpstreamServiceError,
)
from app.domain.hash_chain import verify_chain
from tests.fakes import (
    FakeProposalReader,
    InMemoryAuditTrailRepository,
    InMemorySignatureRepository,
    InMemorySignatureRequestRepository,
)

DOCUMENT = "a" * 64
OTHER_DOCUMENT = "b" * 64
NOW = datetime(2026, 7, 28, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def requests_repo() -> InMemorySignatureRequestRepository:
    return InMemorySignatureRequestRepository()


@pytest.fixture
def signatures_repo() -> InMemorySignatureRepository:
    return InMemorySignatureRepository()


@pytest.fixture
def audit_repo() -> InMemoryAuditTrailRepository:
    return InMemoryAuditTrailRepository()


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


def _create(requests_repo, audit_repo, tenant_id, *, days=30, now=NOW):
    return services.create_signature_request(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        proposal_id=uuid.uuid4(),
        signer_name="Jordan Rivera",
        signer_email="jordan@example.com",
        document_sha256=DOCUMENT,
        expires_in_days=days,
        now=now,
    )


def _sign(requests_repo, signatures_repo, audit_repo, tenant_id, token, **overrides):
    kwargs = {
        "tenant_id": tenant_id,
        "token": token,
        "method": SignatureMethod.TYPED,
        "typed_name": "Jordan Rivera",
        "image_data": None,
        "document_sha256": DOCUMENT,
        "ip_address": "203.0.113.7",
        "user_agent": "Mozilla/5.0",
        "consented_to_electronic_business": True,
        "intent_affirmed": True,
        "now": NOW + timedelta(minutes=5),
    }
    kwargs.update(overrides)
    return services.apply_signature(requests_repo, signatures_repo, audit_repo, **kwargs)


def test_create_starts_pending_with_a_token(requests_repo, audit_repo, tenant_id) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)

    assert created.status is SignatureRequestStatus.PENDING
    assert created.expires_at == NOW + timedelta(days=30)
    assert created.token
    assert created.signer_id != created.id  # distinct identities, not aliased


def test_tokens_are_long_and_unique(requests_repo, audit_repo, tenant_id) -> None:
    tokens = {_create(requests_repo, audit_repo, tenant_id).token for _ in range(25)}

    assert len(tokens) == 25
    # token_urlsafe(32) yields ~43 chars; well past guessing range.
    assert all(len(token) >= 40 for token in tokens)


def test_create_writes_the_opening_audit_entry(requests_repo, audit_repo, tenant_id) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)

    entries = audit_repo.list_for_request(tenant_id, created.id)

    assert [e.event_type for e in entries] == ["request.created"]
    assert entries[0].sequence == 1
    assert verify_chain(entries).is_valid


def test_full_lifecycle_produces_a_valid_three_link_chain(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)
    services.record_document_opened(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        token=created.token,
        ip_address="203.0.113.7",
        user_agent="Mozilla/5.0",
        now=NOW + timedelta(minutes=1),
    )
    _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)

    entries = audit_repo.list_for_request(tenant_id, created.id)

    assert [e.event_type for e in entries] == [
        "request.created",
        "document.opened",
        "signature.applied",
    ]
    assert verify_chain(entries).is_valid


def test_signature_captures_the_evidence_bundle(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)
    signature, request, _event = _sign(
        requests_repo, signatures_repo, audit_repo, tenant_id, created.token
    )

    assert signature.ip_address == "203.0.113.7"
    assert signature.user_agent == "Mozilla/5.0"
    assert signature.document_sha256 == DOCUMENT
    assert signature.consented_to_electronic_business
    assert signature.intent_affirmed
    assert len(signature.signature_hash) == 64
    assert request.status is SignatureRequestStatus.SIGNED
    assert request.signed_at == NOW + timedelta(minutes=5)


def test_signing_rejects_a_different_document(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    """The signer must be agreeing to the exact document on record."""
    created = _create(requests_repo, audit_repo, tenant_id)

    with pytest.raises(DocumentMismatchError):
        _sign(
            requests_repo,
            signatures_repo,
            audit_repo,
            tenant_id,
            created.token,
            document_sha256=OTHER_DOCUMENT,
        )


@pytest.mark.parametrize(
    ("consented", "intent"),
    [(False, True), (True, False), (False, False)],
)
def test_signing_requires_both_consent_and_intent(
    requests_repo, signatures_repo, audit_repo, tenant_id, consented, intent
) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)

    with pytest.raises(ConsentNotGivenError):
        _sign(
            requests_repo,
            signatures_repo,
            audit_repo,
            tenant_id,
            created.token,
            consented_to_electronic_business=consented,
            intent_affirmed=intent,
        )


def test_document_mismatch_is_checked_before_consent(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    """Consent given against a different document isn't consent to this one,
    so the integrity failure is the one worth reporting."""
    created = _create(requests_repo, audit_repo, tenant_id)

    with pytest.raises(DocumentMismatchError):
        _sign(
            requests_repo,
            signatures_repo,
            audit_repo,
            tenant_id,
            created.token,
            document_sha256=OTHER_DOCUMENT,
            consented_to_electronic_business=False,
            intent_affirmed=False,
        )


def test_expired_request_cannot_be_signed(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    created = _create(requests_repo, audit_repo, tenant_id, days=1)

    with pytest.raises(SignatureRequestNotOpenError):
        _sign(
            requests_repo,
            signatures_repo,
            audit_repo,
            tenant_id,
            created.token,
            now=NOW + timedelta(days=2),
        )


def test_cannot_sign_twice(requests_repo, signatures_repo, audit_repo, tenant_id) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)
    _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)

    with pytest.raises(SignatureRequestNotOpenError):
        _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)


def test_unknown_token_is_not_found(requests_repo, signatures_repo, audit_repo, tenant_id) -> None:
    with pytest.raises(SignatureRequestNotFoundError):
        _sign(requests_repo, signatures_repo, audit_repo, tenant_id, "no-such-token")


def test_decline_is_terminal(requests_repo, signatures_repo, audit_repo, tenant_id) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)

    declined = services.decline_signature(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        token=created.token,
        reason="Price too high",
        ip_address="203.0.113.7",
        user_agent=None,
        now=NOW + timedelta(minutes=2),
    )

    assert declined.status is SignatureRequestStatus.DECLINED
    with pytest.raises(SignatureRequestNotOpenError):
        _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)
    assert verify_chain(audit_repo.list_for_request(tenant_id, created.id)).is_valid


def test_void_kills_the_link(requests_repo, signatures_repo, audit_repo, tenant_id) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)

    services.void_signature_request(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        request_id=created.id,
        actor_id=uuid.uuid4(),
        reason="Superseded by a revised quote",
        now=NOW + timedelta(minutes=3),
    )

    with pytest.raises(SignatureRequestNotOpenError):
        _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)


def test_cannot_void_an_already_signed_request(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)
    _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)

    with pytest.raises(SignatureRequestNotOpenError):
        services.void_signature_request(
            requests_repo,
            audit_repo,
            tenant_id=tenant_id,
            request_id=created.id,
            actor_id=None,
        )


def test_effective_status_reports_expired_with_no_writer_involved(
    requests_repo, audit_repo, tenant_id
) -> None:
    """Nothing writes EXPIRED, so correctness must not depend on a sweeper."""
    created = _create(requests_repo, audit_repo, tenant_id, days=1)

    assert created.status is SignatureRequestStatus.PENDING
    assert services.effective_status(created, NOW) is SignatureRequestStatus.PENDING
    assert (
        services.effective_status(created, NOW + timedelta(days=2))
        is SignatureRequestStatus.EXPIRED
    )


def test_reopening_after_signing_adds_no_audit_noise(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)
    _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)
    before = len(audit_repo.list_for_request(tenant_id, created.id))

    services.record_document_opened(
        requests_repo,
        audit_repo,
        tenant_id=tenant_id,
        token=created.token,
        ip_address="203.0.113.7",
        user_agent=None,
        now=NOW + timedelta(hours=1),
    )

    assert len(audit_repo.list_for_request(tenant_id, created.id)) == before


def test_emitted_event_matches_the_canonical_registry_shape(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    """Guards against drifting from `DocumentSignedPayload` in packages/types."""
    created = _create(requests_repo, audit_repo, tenant_id)
    signature, _request, event = _sign(
        requests_repo, signatures_repo, audit_repo, tenant_id, created.token
    )

    assert event.event_name == "esign.document.signed"
    assert set(event.payload) == {
        "proposalId",
        "signerId",
        "signatureHash",
        "ipAddress",
        "signedAt",
    }
    assert event.payload["signatureHash"] == signature.signature_hash
    assert event.payload["signerId"] == str(created.signer_id)
    assert event.payload["ipAddress"] == "203.0.113.7"


def test_audit_trail_returns_a_live_verification(
    requests_repo, signatures_repo, audit_repo, tenant_id
) -> None:
    created = _create(requests_repo, audit_repo, tenant_id)
    _sign(requests_repo, signatures_repo, audit_repo, tenant_id, created.token)

    entries, verification = services.get_audit_trail(
        requests_repo, audit_repo, tenant_id, created.id
    )

    assert len(entries) == 2
    assert verification.is_valid

    entries[0].payload = {"tampered": True}
    _entries, recheck = services.get_audit_trail(requests_repo, audit_repo, tenant_id, created.id)
    assert not recheck.is_valid


# ── T204c: proposal validation ────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["sent", "viewed"])
def test_proposal_a_customer_can_open_is_signable(status: str) -> None:
    proposals = FakeProposalReader(default_status=None)
    proposal_id = uuid.uuid4()
    proposals.register(proposal_id, status)

    result = services.assert_proposal_signable(
        proposals, tenant_id=uuid.uuid4(), proposal_id=proposal_id
    )

    assert result == status


def test_draft_proposal_is_rejected() -> None:
    """A draft's public /view 404s by design, so the signer could never see
    the document they'd be signing."""
    proposals = FakeProposalReader(default_status=None)
    proposal_id = uuid.uuid4()
    proposals.register(proposal_id, "draft")

    with pytest.raises(ProposalNotSignableError):
        services.assert_proposal_signable(
            proposals, tenant_id=uuid.uuid4(), proposal_id=proposal_id
        )


def test_unknown_proposal_is_rejected() -> None:
    """Covers a proposal that doesn't exist *and* one owned by another tenant —
    proposal-service returns 404 for both, and we keep them indistinguishable."""
    proposals = FakeProposalReader(default_status=None)

    with pytest.raises(ProposalNotFoundError):
        services.assert_proposal_signable(
            proposals, tenant_id=uuid.uuid4(), proposal_id=uuid.uuid4()
        )


def test_upstream_failure_is_not_mistaken_for_a_missing_proposal() -> None:
    """proposal-service being down must not read as 'no such proposal'. The
    two need different responses: one is the caller's fault, one is ours."""
    proposals = FakeProposalReader()
    proposals.error = UpstreamServiceError("proposal-service", "connection error")

    with pytest.raises(UpstreamServiceError):
        services.assert_proposal_signable(
            proposals, tenant_id=uuid.uuid4(), proposal_id=uuid.uuid4()
        )


def test_validation_scopes_the_lookup_to_the_calling_tenant() -> None:
    """Cross-tenant protection depends on forwarding the caller's tenant to
    proposal-service, whose RLS then 404s anything outside it. Pin that."""
    proposals = FakeProposalReader()
    tenant_id = uuid.uuid4()
    proposal_id = uuid.uuid4()

    services.assert_proposal_signable(
        proposals, tenant_id=tenant_id, proposal_id=proposal_id
    )

    assert proposals.calls == [(tenant_id, proposal_id)]
