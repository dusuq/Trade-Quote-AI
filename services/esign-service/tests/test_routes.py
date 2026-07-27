"""HTTP-level tests for both the contractor and public routers."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

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
