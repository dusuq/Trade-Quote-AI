"""Tenant isolation (conventions §2 — required for every service).

These verify the *application* never serves one tenant another's data.
Database-enforced RLS is the second layer, defined in 0010_notifications.sql,
and can only be exercised against live Postgres.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

BODY = {
    "channel": "email",
    "recipient": "jane@domain.com",
    "template_name": "quote_delivery",
    "template_vars": {"company_name": "ACME", "view_link": "http://x"},
}


def _send(client: TestClient, tenant_id: uuid.UUID) -> dict:
    response = client.post(
        "/v1/notifications/send", json=BODY, headers={"x-tenant-id": str(tenant_id)}
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_another_tenant_cannot_read_a_message(
    client, api_session, fake_deps, tenant_id, other_tenant_id
) -> None:
    created = _send(client, tenant_id)
    response = client.get(
        f"/v1/notifications/logs/{created['id']}",
        headers={"x-tenant-id": str(other_tenant_id)},
    )
    assert response.status_code == 404


def test_logs_listing_never_crosses_tenants(
    client, api_session, fake_deps, tenant_id, other_tenant_id
) -> None:
    mine = _send(client, tenant_id)
    theirs = _send(client, other_tenant_id)

    my_ids = {
        row["id"]
        for row in client.get(
            "/v1/notifications/logs", headers={"x-tenant-id": str(tenant_id)}
        ).json()
    }

    assert mine["id"] in my_ids
    assert theirs["id"] not in my_ids


def test_templates_never_cross_tenants(
    client, api_session, fake_deps, tenant_id, other_tenant_id
) -> None:
    client.post(
        "/v1/notifications/templates",
        json={"name": "quote_delivery", "channel": "email", "body_template": "mine"},
        headers={"x-tenant-id": str(tenant_id)},
    )

    others = client.get(
        "/v1/notifications/templates", headers={"x-tenant-id": str(other_tenant_id)}
    ).json()

    assert others == []
