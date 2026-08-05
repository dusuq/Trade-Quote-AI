import uuid

from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "analytics-service"


def test_routes_require_tenant_id_header(client: TestClient) -> None:
    # Missing header -> 401
    res = client.get("/v1/analytics/overview")
    assert res.status_code == 401
    assert "Missing required x-tenant-id" in res.json()["detail"]

    # Malformed header -> 400
    res_bad = client.get("/v1/analytics/overview", headers={"x-tenant-id": "invalid-uuid"})
    assert res_bad.status_code == 400
    assert "Invalid x-tenant-id header UUID format" in res_bad.json()["detail"]


def test_analytics_endpoints_workflow(client: TestClient, tenant_a_id: uuid.UUID) -> None:
    headers = {"x-tenant-id": str(tenant_a_id)}
    quote_id = str(uuid.uuid4())
    customer_id = str(uuid.uuid4())

    # 1. Ingest event
    ingest_payload = {
        "quote_id": quote_id,
        "customer_id": customer_id,
        "customer_name": "ACME Industries",
        "event_type": "quote.accepted",
        "trade": "electrical",
        "amount_minor": 150000,
    }
    res_ingest = client.post("/v1/analytics/events/ingest", json=ingest_payload, headers=headers)
    assert res_ingest.status_code == 201
    assert res_ingest.json()["status"] == "recorded"

    # 2. Get Overview
    res_overview = client.get("/v1/analytics/overview", headers=headers)
    assert res_overview.status_code == 200
    overview_data = res_overview.json()
    assert overview_data["total_accepted_value_minor"] == 150000
    assert overview_data["accepted_count"] == 1

    # 3. Get Trades
    res_trades = client.get("/v1/analytics/trades", headers=headers)
    assert res_trades.status_code == 200
    trades_data = res_trades.json()
    assert len(trades_data) == 1
    assert trades_data[0]["trade"] == "electrical"
    assert trades_data[0]["total_revenue_minor"] == 150000

    # 4. Get Customers
    res_cust = client.get("/v1/analytics/customers", headers=headers)
    assert res_cust.status_code == 200
    cust_data = res_cust.json()
    assert len(cust_data) == 1
    assert cust_data[0]["customer_name"] == "ACME Industries"
    assert cust_data[0]["lifetime_value_minor"] == 150000
