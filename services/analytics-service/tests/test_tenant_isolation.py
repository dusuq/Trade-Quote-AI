import uuid
from fastapi.testclient import TestClient


def test_enforces_strict_tenant_isolation(
    client: TestClient, tenant_a_id: uuid.UUID, tenant_b_id: uuid.UUID
) -> None:
    headers_a = {"x-tenant-id": str(tenant_a_id)}
    headers_b = {"x-tenant-id": str(tenant_b_id)}

    # Ingest event for Tenant A
    client.post(
        "/v1/analytics/events/ingest",
        json={
            "quote_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "customer_name": "Tenant A Customer",
            "event_type": "quote.accepted",
            "trade": "electrical",
            "amount_minor": 500000,
        },
        headers=headers_a,
    )

    # Ingest event for Tenant B
    client.post(
        "/v1/analytics/events/ingest",
        json={
            "quote_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "customer_name": "Tenant B Customer",
            "event_type": "quote.accepted",
            "trade": "plumbing",
            "amount_minor": 200000,
        },
        headers=headers_b,
    )

    # Tenant A Overview should ONLY see Tenant A data ($5000.00)
    overview_a = client.get("/v1/analytics/overview", headers=headers_a).json()
    assert overview_a["total_accepted_value_minor"] == 500000
    assert overview_a["accepted_count"] == 1

    # Tenant B Overview should ONLY see Tenant B data ($2000.00)
    overview_b = client.get("/v1/analytics/overview", headers=headers_b).json()
    assert overview_b["total_accepted_value_minor"] == 200000
    assert overview_b["accepted_count"] == 1

    # Tenant A Customer List should not leak Tenant B
    cust_a = client.get("/v1/analytics/customers", headers=headers_a).json()
    assert len(cust_a) == 1
    assert cust_a[0]["customer_name"] == "Tenant A Customer"

    # Tenant B Customer List should not leak Tenant A
    cust_b = client.get("/v1/analytics/customers", headers=headers_b).json()
    assert len(cust_b) == 1
    assert cust_b[0]["customer_name"] == "Tenant B Customer"
