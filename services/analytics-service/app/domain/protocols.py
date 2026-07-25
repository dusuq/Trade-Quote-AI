import uuid
from typing import Protocol

from app.domain.models import AnalyticsOverview, CustomerLTV, QuoteEventRecord, TradeBreakdown


class AnalyticsRepositoryProtocol(Protocol):
    def record_quote_event(self, event: QuoteEventRecord) -> None:
        ...

    def get_overview(self, tenant_id: uuid.UUID) -> AnalyticsOverview:
        ...

    def get_trade_breakdowns(self, tenant_id: uuid.UUID) -> list[TradeBreakdown]:
        ...

    def get_customer_ltv_leaderboard(
        self, tenant_id: uuid.UUID, limit: int = 10
    ) -> list[CustomerLTV]:
        ...
