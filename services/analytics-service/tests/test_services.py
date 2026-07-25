import uuid
from app.application.services import AnalyticsService
from app.infrastructure.repositories import InMemoryAnalyticsRepository


def test_analytics_service_event_ingestion_and_overview() -> None:
    repo = InMemoryAnalyticsRepository()
    service = AnalyticsService(repo)
    tenant_id = uuid.uuid4()

    q1 = uuid.uuid4()
    q2 = uuid.uuid4()
    c1 = uuid.uuid4()

    service.ingest_quote_event(
        tenant_id=tenant_id,
        quote_id=q1,
        customer_id=c1,
        customer_name="John Doe",
        event_type="quote.created",
        trade="electrical",
        amount_minor=100000,
    )
    service.ingest_quote_event(
        tenant_id=tenant_id,
        quote_id=q1,
        customer_id=c1,
        customer_name="John Doe",
        event_type="quote.accepted",
        trade="electrical",
        amount_minor=100000,
    )
    service.ingest_quote_event(
        tenant_id=tenant_id,
        quote_id=q2,
        customer_id=c1,
        customer_name="John Doe",
        event_type="quote.sent",
        trade="plumbing",
        amount_minor=200000,
    )

    overview = service.get_overview(tenant_id)
    assert overview.total_quotes_count == 2
    assert overview.accepted_count == 1
    assert overview.sent_count == 1
    assert overview.conversion_rate_bps == 5000 # 50%
    assert overview.total_accepted_value_minor == 100000
    assert overview.average_ticket_minor == 100000


def test_analytics_service_trade_breakdown_and_ltv() -> None:
    repo = InMemoryAnalyticsRepository()
    service = AnalyticsService(repo)
    tenant_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    service.ingest_quote_event(
        tenant_id=tenant_id,
        quote_id=uuid.uuid4(),
        customer_id=cust_id,
        customer_name="Apex Corp",
        event_type="quote.accepted",
        trade="hvac",
        amount_minor=500000,
    )
    service.ingest_quote_event(
        tenant_id=tenant_id,
        quote_id=uuid.uuid4(),
        customer_id=cust_id,
        customer_name="Apex Corp",
        event_type="quote.accepted",
        trade="hvac",
        amount_minor=300000,
    )

    trades = service.get_trade_breakdowns(tenant_id)
    assert len(trades) == 1
    assert trades[0].trade == "hvac"
    assert trades[0].accepted_count == 2
    assert trades[0].total_revenue_minor == 800000

    ltv_list = service.get_customer_ltv(tenant_id, limit=5)
    assert len(ltv_list) == 1
    assert ltv_list[0].customer_name == "Apex Corp"
    assert ltv_list[0].lifetime_value_minor == 800000
    assert ltv_list[0].is_repeat_customer is True
