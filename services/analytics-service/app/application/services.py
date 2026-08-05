import uuid

from app.domain.models import AnalyticsOverview, CustomerLTV, QuoteEventRecord, TradeBreakdown
from app.domain.protocols import AnalyticsRepositoryProtocol


class AnalyticsService:
    def __init__(self, repo: AnalyticsRepositoryProtocol) -> None:
        self.repo = repo

    def ingest_quote_event(
        self,
        tenant_id: uuid.UUID,
        quote_id: uuid.UUID,
        customer_id: uuid.UUID,
        customer_name: str | None,
        event_type: str,
        trade: str,
        amount_minor: int,
    ) -> QuoteEventRecord:
        resolved_name = (
            customer_name.strip()
            if (customer_name and customer_name.strip())
            else f"Customer #{str(customer_id)[:8]}"
        )
        event = QuoteEventRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            quote_id=quote_id,
            customer_id=customer_id,
            customer_name=resolved_name,
            event_type=event_type,
            trade=trade.lower(),
            amount_minor=amount_minor,
        )
        self.repo.record_quote_event(event)
        return event

    def get_overview(self, tenant_id: uuid.UUID) -> AnalyticsOverview:
        return self.repo.get_overview(tenant_id)

    def get_trade_breakdowns(self, tenant_id: uuid.UUID) -> list[TradeBreakdown]:
        return self.repo.get_trade_breakdowns(tenant_id)

    def get_customer_ltv(
        self, tenant_id: uuid.UUID, limit: int = 10
    ) -> list[CustomerLTV]:
        return self.repo.get_customer_ltv_leaderboard(tenant_id, limit=limit)
