import uuid

from app.domain.models import AnalyticsOverview, CustomerLTV, TradeBreakdown


def test_analytics_overview_instantiation() -> None:
    tenant_id = uuid.uuid4()
    overview = AnalyticsOverview(
        tenant_id=tenant_id,
        total_quotes_count=10,
        draft_count=2,
        sent_count=3,
        accepted_count=4,
        rejected_count=1,
        total_accepted_value_minor=400000,
        total_pipeline_value_minor=1000000,
        conversion_rate_bps=4000,
        average_ticket_minor=100000,
        projected_monthly_revenue_minor=640000,
    )
    assert overview.tenant_id == tenant_id
    assert overview.total_quotes_count == 10
    assert overview.conversion_rate_bps == 4000
    assert overview.currency == "USD"


def test_trade_breakdown_instantiation() -> None:
    tb = TradeBreakdown(
        trade="electrical",
        quotes_count=5,
        accepted_count=3,
        total_revenue_minor=300000,
        conversion_rate_bps=6000,
    )
    assert tb.trade == "electrical"
    assert tb.conversion_rate_bps == 6000


def test_customer_ltv_instantiation() -> None:
    cust_id = uuid.uuid4()
    ltv = CustomerLTV(
        customer_id=cust_id,
        customer_name="Apex Commercial",
        total_quotes_count=4,
        accepted_quotes_count=2,
        lifetime_value_minor=500000,
        is_repeat_customer=True,
    )
    assert ltv.is_repeat_customer is True
    assert ltv.lifetime_value_minor == 500000
