"""Tenant isolation (conventions §2 — required for every service).

These prove the *application* never serves one tenant another's AI usage.
Database-enforced RLS is the second layer, defined in 0009_ai_service.sql,
and can only be exercised against live Postgres — that runs under T311.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

TEXT_BODY = {
    "text": "Replace the panel with a 200 amp and install twelve LED lights",
    "customer_id": str(uuid.uuid4()),
}


def test_usage_never_crosses_tenants(
    client: TestClient, api_session, fake_deps, tenant_id, other_tenant_id
) -> None:
    client.post(
        "/v1/ai/text-to-quote", json=TEXT_BODY, headers={"x-tenant-id": str(tenant_id)}
    )

    mine = client.get("/v1/ai/usage", headers={"x-tenant-id": str(tenant_id)}).json()
    theirs = client.get("/v1/ai/usage", headers={"x-tenant-id": str(other_tenant_id)}).json()

    assert len(mine) == 1
    assert theirs == []


def test_each_tenant_sees_only_its_own_rows(
    client: TestClient, api_session, fake_deps, tenant_id, other_tenant_id
) -> None:
    client.post(
        "/v1/ai/text-to-quote", json=TEXT_BODY, headers={"x-tenant-id": str(tenant_id)}
    )
    client.post(
        "/v1/ai/text-to-quote", json=TEXT_BODY, headers={"x-tenant-id": str(other_tenant_id)}
    )

    mine = client.get("/v1/ai/usage", headers={"x-tenant-id": str(tenant_id)}).json()
    theirs = client.get("/v1/ai/usage", headers={"x-tenant-id": str(other_tenant_id)}).json()

    assert len(mine) == 1
    assert len(theirs) == 1
    assert mine[0]["id"] != theirs[0]["id"]


def test_spend_cap_is_scoped_per_tenant(
    client: TestClient, api_session, fake_deps, tenant_id, other_tenant_id, monkeypatch
) -> None:
    """One tenant exhausting its budget must not lock anyone else out."""
    monkeypatch.setattr("app.interface.routes.settings.daily_spend_cap_minor", 1)
    client.post(
        "/v1/ai/text-to-quote", json=TEXT_BODY, headers={"x-tenant-id": str(tenant_id)}
    )

    blocked = client.post(
        "/v1/ai/text-to-quote", json=TEXT_BODY, headers={"x-tenant-id": str(tenant_id)}
    )
    unaffected = client.post(
        "/v1/ai/text-to-quote", json=TEXT_BODY, headers={"x-tenant-id": str(other_tenant_id)}
    )

    assert blocked.status_code == 429
    assert unaffected.status_code == 201
