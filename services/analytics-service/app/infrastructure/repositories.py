import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import AnalyticsOverview, CustomerLTV, QuoteEventRecord, TradeBreakdown
from app.domain.protocols import AnalyticsRepositoryProtocol
from app.infrastructure.models import AnalyticsEventORM


class InMemoryAnalyticsRepository(AnalyticsRepositoryProtocol):
    """In-memory fake repository for test suites."""

    def __init__(self) -> None:
        self.events: list[QuoteEventRecord] = []

    def record_quote_event(self, event: QuoteEventRecord) -> None:
        self.events.append(event)

    def get_overview(self, tenant_id: uuid.UUID) -> AnalyticsOverview:
        tenant_events = [e for e in self.events if e.tenant_id == tenant_id]

        total_quotes = len({e.quote_id for e in tenant_events})
        accepted_events = [e for e in tenant_events if e.event_type == "quote.accepted"]
        sent_events = [e for e in tenant_events if e.event_type == "quote.sent"]
        rejected_events = [e for e in tenant_events if e.event_type == "quote.rejected"]
        created_events = [e for e in tenant_events if e.event_type == "quote.created"]

        accepted_count = len({e.quote_id for e in accepted_events})
        sent_count = len({e.quote_id for e in sent_events})
        rejected_count = len({e.quote_id for e in rejected_events})

        # Latest event per quote determines current state
        latest_quote_amounts: dict[uuid.UUID, int] = {}
        for e in tenant_events:
            latest_quote_amounts[e.quote_id] = e.amount_minor

        total_accepted_val = sum(
            latest_quote_amounts[e.quote_id] for e in accepted_events
        )
        total_pipeline_val = sum(latest_quote_amounts.values())

        draft_count = max(0, total_quotes - (accepted_count + sent_count + rejected_count))
        if draft_count == 0 and total_quotes == 0 and len(created_events) > 0:
            draft_count = len(created_events)

        conversion_rate_bps = (
            int((accepted_count / total_quotes) * 10000) if total_quotes > 0 else 0
        )
        avg_ticket = (
            int(total_accepted_val / accepted_count) if accepted_count > 0 else 0
        )
        # Revenue forecast assumes current pipeline maintains historical conversion rate
        projected_monthly = total_accepted_val + int(
            (total_pipeline_val - total_accepted_val) * (conversion_rate_bps / 10000.0)
        )

        return AnalyticsOverview(
            tenant_id=tenant_id,
            total_quotes_count=total_quotes,
            draft_count=draft_count,
            sent_count=sent_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            total_accepted_value_minor=total_accepted_val,
            total_pipeline_value_minor=total_pipeline_val,
            conversion_rate_bps=conversion_rate_bps,
            average_ticket_minor=avg_ticket,
            projected_monthly_revenue_minor=projected_monthly,
        )

    def get_trade_breakdowns(self, tenant_id: uuid.UUID) -> list[TradeBreakdown]:
        tenant_events = [e for e in self.events if e.tenant_id == tenant_id]

        trades: dict[str, list[QuoteEventRecord]] = defaultdict(list)
        for e in tenant_events:
            trades[e.trade].append(e)

        breakdowns: list[TradeBreakdown] = []
        for trade_name, events in trades.items():
            unique_quotes = {e.quote_id for e in events}
            accepted = [e for e in events if e.event_type == "quote.accepted"]
            accepted_quotes = {e.quote_id for e in accepted}

            total_rev = sum(e.amount_minor for e in accepted)
            conv_bps = (
                int((len(accepted_quotes) / len(unique_quotes)) * 10000)
                if unique_quotes
                else 0
            )

            breakdowns.append(
                TradeBreakdown(
                    trade=trade_name,
                    quotes_count=len(unique_quotes),
                    accepted_count=len(accepted_quotes),
                    total_revenue_minor=total_rev,
                    conversion_rate_bps=conv_bps,
                )
            )

        return breakdowns

    def get_customer_ltv_leaderboard(
        self, tenant_id: uuid.UUID, limit: int = 10
    ) -> list[CustomerLTV]:
        tenant_events = [e for e in self.events if e.tenant_id == tenant_id]

        customers: dict[uuid.UUID, list[QuoteEventRecord]] = defaultdict(list)
        for e in tenant_events:
            customers[e.customer_id].append(e)

        leaderboard: list[CustomerLTV] = []
        for cust_id, events in customers.items():
            cust_name = events[0].customer_name
            unique_quotes = {e.quote_id for e in events}
            accepted = [e for e in events if e.event_type == "quote.accepted"]
            accepted_quotes = {e.quote_id for e in accepted}
            ltv = sum(e.amount_minor for e in accepted)

            leaderboard.append(
                CustomerLTV(
                    customer_id=cust_id,
                    customer_name=cust_name,
                    total_quotes_count=len(unique_quotes),
                    accepted_quotes_count=len(accepted_quotes),
                    lifetime_value_minor=ltv,
                    is_repeat_customer=len(accepted_quotes) > 1,
                )
            )

        leaderboard.sort(key=lambda x: x.lifetime_value_minor, reverse=True)
        return leaderboard[:limit]


class SqlAlchemyAnalyticsRepository(AnalyticsRepositoryProtocol):
    """Production SQLAlchemy repository implementation."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_quote_event(self, event: QuoteEventRecord) -> None:
        orm = AnalyticsEventORM(
            id=event.id,
            tenant_id=event.tenant_id,
            quote_id=event.quote_id,
            customer_id=event.customer_id,
            customer_name=event.customer_name,
            event_type=event.event_type,
            trade=event.trade,
            amount_minor=event.amount_minor,
            created_at=event.created_at,
        )
        self.session.add(orm)
        self.session.flush()

    def get_overview(self, tenant_id: uuid.UUID) -> AnalyticsOverview:
        stmt = select(AnalyticsEventORM).where(AnalyticsEventORM.tenant_id == tenant_id)
        orms = list(self.session.scalars(stmt).all())

        in_mem = InMemoryAnalyticsRepository()
        for o in orms:
            in_mem.record_quote_event(
                QuoteEventRecord(
                    id=o.id,
                    tenant_id=o.tenant_id,
                    quote_id=o.quote_id,
                    customer_id=o.customer_id,
                    customer_name=o.customer_name,
                    event_type=o.event_type,
                    trade=o.trade,
                    amount_minor=o.amount_minor,
                    created_at=o.created_at,
                )
            )
        return in_mem.get_overview(tenant_id)

    def get_trade_breakdowns(self, tenant_id: uuid.UUID) -> list[TradeBreakdown]:
        stmt = select(AnalyticsEventORM).where(AnalyticsEventORM.tenant_id == tenant_id)
        orms = list(self.session.scalars(stmt).all())

        in_mem = InMemoryAnalyticsRepository()
        for o in orms:
            in_mem.record_quote_event(
                QuoteEventRecord(
                    id=o.id,
                    tenant_id=o.tenant_id,
                    quote_id=o.quote_id,
                    customer_id=o.customer_id,
                    customer_name=o.customer_name,
                    event_type=o.event_type,
                    trade=o.trade,
                    amount_minor=o.amount_minor,
                    created_at=o.created_at,
                )
            )
        return in_mem.get_trade_breakdowns(tenant_id)

    def get_customer_ltv_leaderboard(
        self, tenant_id: uuid.UUID, limit: int = 10
    ) -> list[CustomerLTV]:
        stmt = select(AnalyticsEventORM).where(AnalyticsEventORM.tenant_id == tenant_id)
        orms = list(self.session.scalars(stmt).all())

        in_mem = InMemoryAnalyticsRepository()
        for o in orms:
            in_mem.record_quote_event(
                QuoteEventRecord(
                    id=o.id,
                    tenant_id=o.tenant_id,
                    quote_id=o.quote_id,
                    customer_id=o.customer_id,
                    customer_name=o.customer_name,
                    event_type=o.event_type,
                    trade=o.trade,
                    amount_minor=o.amount_minor,
                    created_at=o.created_at,
                )
            )
        return in_mem.get_customer_ltv_leaderboard(tenant_id, limit=limit)
