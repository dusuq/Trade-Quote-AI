"""Tenant isolation (conventions §2 — required for every service).

Note what these prove and what they don't: they verify the *application*
never serves one tenant another's signature data. Database-enforced RLS is
the second layer, defined in 0008_esign.sql, and can only be exercised
against live Postgres — that runs under T311.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

DOCUMENT = "a" * 64


def _create(client: TestClient, tenant_id: uuid.UUID, resolver) -> dict:
    response = client.post(
        "/v1/signature-requests",
        json={
            "proposal_id": str(uuid.uuid4()),
            "signer_name": "Jordan Rivera",
            "signer_email": "jordan@example.com",
            "document_sha256": DOCUMENT,
        },
        headers={"x-tenant-id": str(tenant_id)},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    resolver.register(body["token"], tenant_id)
    return body


def test_another_tenant_cannot_read_a_signature_request(
    client, api_session, resolver, tenant_id, other_tenant_id
) -> None:
    created = _create(client, tenant_id, resolver)

    response = client.get(
        f"/v1/signature-requests/{created['id']}",
        headers={"x-tenant-id": str(other_tenant_id)},
    )

    assert response.status_code == 404


def test_another_tenant_cannot_read_the_audit_trail(
    client, api_session, resolver, tenant_id, other_tenant_id
) -> None:
    created = _create(client, tenant_id, resolver)

    response = client.get(
        f"/v1/signature-requests/{created['id']}/audit",
        headers={"x-tenant-id": str(other_tenant_id)},
    )

    assert response.status_code == 404


def test_another_tenant_cannot_void_a_signature_request(
    client, api_session, resolver, tenant_id, other_tenant_id
) -> None:
    created = _create(client, tenant_id, resolver)

    response = client.post(
        f"/v1/signature-requests/{created['id']}/void",
        json={},
        headers={"x-tenant-id": str(other_tenant_id)},
    )

    assert response.status_code == 404


def test_listing_never_crosses_tenants(
    client, api_session, resolver, tenant_id, other_tenant_id
) -> None:
    mine = _create(client, tenant_id, resolver)
    theirs = _create(client, other_tenant_id, resolver)

    my_ids = {
        row["id"]
        for row in client.get(
            "/v1/signature-requests", headers={"x-tenant-id": str(tenant_id)}
        ).json()
    }

    assert mine["id"] in my_ids
    assert theirs["id"] not in my_ids


def test_a_token_only_resolves_within_its_owning_tenant(
    client, api_session, resolver, tenant_id, other_tenant_id
) -> None:
    """Belt and braces: even if a token leaked and the resolver were tricked
    into pointing at the wrong tenant, the tenant-scoped lookup finds nothing.
    """
    created = _create(client, tenant_id, resolver)
    resolver.register(created["token"], other_tenant_id)

    assert client.get(f"/v1/sign/{created['token']}").status_code == 404
