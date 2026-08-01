"""HTTP-level tests for both the contractor and public routers."""

from __future__ import annotations

import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.domain.errors import UpstreamServiceError
from app.infrastructure.models import SignatureAuditEventORM, SignatureRequestORM

DOCUMENT = "a" * 64
OTHER_DOCUMENT = "b" * 64

SIGN_BODY = {
    "method": "typed",
    "typed_name": "Jordan Rivera",
    "document_sha256": DOCUMENT,
    "consented_to_electronic_business": True,
    "intent_affirmed": True,
}


def _create(client: TestClient, auth_header, resolver, tenant_id, document=DOCUMENT) -> dict:
    response = client.post(
        "/v1/signature-requests",
        json={
            "proposal_id": str(uuid.uuid4()),
            "signer_name": "Jordan Rivera",
            "signer_email": "jordan@example.com",
            "document_sha256": document,
        },
        headers=auth_header,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    resolver.register(body["token"], tenant_id)
    return body


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "healthy"


def test_create_returns_a_token_and_signing_path(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    body = _create(client, auth_header, resolver, tenant_id)

    assert body["status"] == "pending"
    assert body["signing_path"] == f"/v1/sign/{body['token']}"
    assert len(body["token"]) >= 40
    assert body["signature"] is None


def test_missing_tenant_header_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/v1/signature-requests",
        json={
            "proposal_id": str(uuid.uuid4()),
            "signer_name": "Jordan Rivera",
            "signer_email": "jordan@example.com",
            "document_sha256": DOCUMENT,
        },
    )
    assert response.status_code == 401


def test_list_omits_tokens(client, api_session, resolver, auth_header, tenant_id) -> None:
    """A list endpoint must not spray live signing capabilities."""
    _create(client, auth_header, resolver, tenant_id)

    body = client.get("/v1/signature-requests", headers=auth_header).json()

    assert len(body) >= 1
    assert all("token" not in row for row in body)


def test_public_context_never_leaks_tenant_or_internal_ids(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    created = _create(client, auth_header, resolver, tenant_id)

    body = client.get(f"/v1/sign/{created['token']}").json()

    assert body["can_sign"] is True
    assert body["signer_name"] == "Jordan Rivera"
    assert "tenant_id" not in body
    assert "signer_id" not in body
    assert "token" not in body


def test_public_signing_happy_path(client, api_session, resolver, auth_header, tenant_id) -> None:
    created = _create(client, auth_header, resolver, tenant_id)

    response = client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["signer_name"] == "Jordan Rivera"
    assert body["document_sha256"] == DOCUMENT
    assert len(body["signature_hash"]) == 64
    assert body["intent_affirmed"] is True


def test_signing_records_the_forwarded_client_ip(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    """The gateway overwrites x-forwarded-for with the real peer, so this is
    the signer's address rather than the proxy's."""
    created = _create(client, auth_header, resolver, tenant_id)

    response = client.post(
        f"/v1/sign/{created['token']}",
        json=SIGN_BODY,
        headers={"x-forwarded-for": "198.51.100.5, 10.0.0.1", "user-agent": "Safari/17"},
    )

    body = response.json()
    assert body["ip_address"] == "198.51.100.5"
    assert body["user_agent"] == "Safari/17"


def test_signing_a_different_document_is_rejected(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    created = _create(client, auth_header, resolver, tenant_id)

    response = client.post(
        f"/v1/sign/{created['token']}", json={**SIGN_BODY, "document_sha256": OTHER_DOCUMENT}
    )

    assert response.status_code == 409


def test_signing_without_consent_is_rejected(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    created = _create(client, auth_header, resolver, tenant_id)

    response = client.post(
        f"/v1/sign/{created['token']}",
        json={**SIGN_BODY, "consented_to_electronic_business": False},
    )

    assert response.status_code == 422


def test_typed_signature_requires_a_typed_name(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    created = _create(client, auth_header, resolver, tenant_id)

    response = client.post(
        f"/v1/sign/{created['token']}", json={**SIGN_BODY, "typed_name": "   "}
    )

    assert response.status_code == 422


def test_signing_twice_conflicts(client, api_session, resolver, auth_header, tenant_id) -> None:
    created = _create(client, auth_header, resolver, tenant_id)
    client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY)

    response = client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY)

    assert response.status_code == 409


def test_unknown_token_is_404(client, api_session, resolver) -> None:
    assert client.get("/v1/sign/not-a-real-token").status_code == 404
    assert client.post("/v1/sign/not-a-real-token", json=SIGN_BODY).status_code == 404


def test_decline_closes_the_request(client, api_session, resolver, auth_header, tenant_id) -> None:
    created = _create(client, auth_header, resolver, tenant_id)

    response = client.post(
        f"/v1/sign/{created['token']}/decline", json={"reason": "Going with another quote"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "declined"
    assert response.json()["can_sign"] is False
    assert client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY).status_code == 409


def test_audit_endpoint_returns_the_chain_and_verifies_it(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    created = _create(client, auth_header, resolver, tenant_id)
    client.get(f"/v1/sign/{created['token']}")
    client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY)

    body = client.get(f"/v1/signature-requests/{created['id']}/audit", headers=auth_header).json()

    assert [entry["event_type"] for entry in body["entries"]] == [
        "request.created",
        "document.opened",
        "signature.applied",
    ]
    assert body["verification"]["is_valid"] is True
    assert body["verification"]["entry_count"] == 3
    assert body["entries"][0]["prev_hash"] == "0" * 64


def test_detail_includes_the_signature_once_signed(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    created = _create(client, auth_header, resolver, tenant_id)
    client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY)

    body = client.get(f"/v1/signature-requests/{created['id']}", headers=auth_header).json()

    assert body["status"] == "signed"
    assert body["signature"]["signer_name"] == "Jordan Rivera"


def test_void_blocks_further_signing(client, api_session, resolver, auth_header, tenant_id) -> None:
    created = _create(client, auth_header, resolver, tenant_id)

    voided = client.post(
        f"/v1/signature-requests/{created['id']}/void",
        json={"reason": "Superseded"},
        headers=auth_header,
    )

    assert voided.status_code == 200
    assert voided.json()["status"] == "voided"
    assert client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY).status_code == 409


def test_void_of_a_signed_request_conflicts(
    client, api_session, resolver, auth_header, tenant_id
) -> None:
    created = _create(client, auth_header, resolver, tenant_id)
    client.post(f"/v1/sign/{created['token']}", json=SIGN_BODY)

    response = client.post(
        f"/v1/signature-requests/{created['id']}/void", json={}, headers=auth_header
    )

    assert response.status_code == 409


def test_unknown_request_id_is_404(client, api_session, auth_header) -> None:
    response = client.get(f"/v1/signature-requests/{uuid.uuid4()}", headers=auth_header)
    assert response.status_code == 404


# ── T204c: proposal validation at the create endpoint ─────────────────────────


def _create_payload() -> dict:
    return {
        "proposal_id": str(uuid.uuid4()),
        "signer_name": "Jordan Rivera",
        "signer_email": "jordan@example.com",
        "document_sha256": DOCUMENT,
    }


def test_create_against_a_draft_proposal_is_409(
    client, api_session, auth_header, proposals
) -> None:
    payload = _create_payload()
    proposals.register(uuid.UUID(payload["proposal_id"]), "draft")

    response = client.post("/v1/signature-requests", json=payload, headers=auth_header)

    assert response.status_code == 409
    assert "draft" in response.json()["detail"]


def test_create_against_an_unknown_proposal_is_404(
    client, api_session, auth_header, proposals
) -> None:
    proposals.default_status = None

    response = client.post(
        "/v1/signature-requests", json=_create_payload(), headers=auth_header
    )

    assert response.status_code == 404


def test_create_is_502_when_proposal_service_is_unreachable(
    client, api_session, auth_header, proposals
) -> None:
    """Fail closed: if we can't confirm the document exists, we don't open a
    legal audit trail against it."""
    proposals.error = UpstreamServiceError("proposal-service", "connection error: refused")

    response = client.post(
        "/v1/signature-requests", json=_create_payload(), headers=auth_header
    )

    assert response.status_code == 502


def test_rejected_create_writes_nothing_to_the_database(
    client, api_session, auth_header, proposals, tenant_id
) -> None:
    """A rejected create must leave no row and no audit entry behind.

    Note this does *not* pin ADR-0003 rule 3 on its own — a rollback would
    produce the same empty tables. `test_proposal_is_read_before_any_
    transaction_opens` is the test that pins the ordering.
    """
    payload = _create_payload()
    proposals.register(uuid.UUID(payload["proposal_id"]), "draft")

    client.post("/v1/signature-requests", json=payload, headers=auth_header)

    assert api_session.scalar(select(func.count()).select_from(SignatureRequestORM)) == 0
    assert api_session.scalar(select(func.count()).select_from(SignatureAuditEventORM)) == 0


def test_create_forwards_the_callers_tenant_to_proposal_service(
    client, api_session, auth_header, proposals, tenant_id
) -> None:
    """Cross-tenant protection leans on proposal-service's own RLS, which only
    applies to the tenant we forward — so forwarding the *caller's* tenant is
    the whole control."""
    payload = _create_payload()

    client.post("/v1/signature-requests", json=payload, headers=auth_header)

    assert proposals.calls == [(tenant_id, uuid.UUID(payload["proposal_id"]))]


def test_proposal_is_read_before_any_transaction_opens(
    client, engine, auth_header, proposals, monkeypatch
) -> None:
    """ADR-0003 rule 3: no network I/O while a DB transaction is open.

    Asserting on ordering rather than on the absence of rows, because a
    rollback also leaves the tables empty — only the sequence distinguishes
    "validated first" from "validated while holding a pooled connection".
    """
    events: list[str] = []
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    @contextmanager
    def _tracking_session(_tenant_id: uuid.UUID):
        events.append("txn.open")
        try:
            yield session
        finally:
            events.append("txn.close")

    monkeypatch.setattr("app.interface.routes.tenant_session", _tracking_session)

    inner = proposals.get_status

    def _tracked(tenant_id: uuid.UUID, proposal_id: uuid.UUID):
        events.append("proposal.read")
        return inner(tenant_id, proposal_id)

    monkeypatch.setattr(proposals, "get_status", _tracked)

    response = client.post(
        "/v1/signature-requests", json=_create_payload(), headers=auth_header
    )
    assert response.status_code == 201, response.text

    session.rollback()
    session.close()

    assert events.index("proposal.read") < events.index("txn.open")
