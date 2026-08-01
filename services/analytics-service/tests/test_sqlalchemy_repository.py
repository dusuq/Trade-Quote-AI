import uuid
from sqlalchemy.orm import Session

from app.domain.models import QuoteEventRecord
from app.infrastructure.repositories import SqlAlchemyAnalyticsRepository


def test_sqlalchemy_analytics_repository_record_and_query(db_session: Session) -> None:
    repo = SqlAlchemyAnalyticsRepository(db_session)
    tenant_id = uuid.uuid4()
    quote_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    event = QuoteEventRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        quote_id=quote_id,
        customer_id=customer_id,
        customer_name="Acme Corp",
        event_type="quote.accepted",
        trade="electrical",
        amount_minor=150000,
    )

    repo.record_quote_event(event)

    overview = repo.get_overview(tenant_id)
    assert overview.tenant_id == tenant_id
    assert overview.accepted_count == 1
    assert overview.total_accepted_value_minor == 150000

    trades = repo.get_trade_breakdowns(tenant_id)
    assert len(trades) == 1
    assert trades[0].trade == "electrical"
    assert trades[0].total_revenue_minor == 150000

    leaderboard = repo.get_customer_ltv_leaderboard(tenant_id)
    assert len(leaderboard) == 1
    assert leaderboard[0].customer_name == "Acme Corp"
    assert leaderboard[0].lifetime_value_minor == 150000


def test_sqlalchemy_analytics_repository_tenant_isolation(db_session: Session) -> None:
    repo = SqlAlchemyAnalyticsRepository(db_session)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    event_a = QuoteEventRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_a,
        quote_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        customer_name="Customer A",
        event_type="quote.accepted",
        trade="hvac",
        amount_minor=300000,
    )
    event_b = QuoteEventRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_b,
        quote_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        customer_name="Customer B",
        event_type="quote.accepted",
        trade="plumbing",
        amount_minor=400000,
    )

    repo.record_quote_event(event_a)
    repo.record_quote_event(event_b)

    overview_a = repo.get_overview(tenant_a)
    assert overview_a.total_accepted_value_minor == 300000
    assert overview_a.accepted_count == 1

    overview_b = repo.get_overview(tenant_b)
    assert overview_b.total_accepted_value_minor == 400000
    assert overview_b.accepted_count == 1
