import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class AnalyticsOverview:
    tenant_id: uuid.UUID
    total_quotes_count: int
    draft_count: int
    sent_count: int
    accepted_count: int
    rejected_count: int
    total_accepted_value_minor: int
    total_pipeline_value_minor: int
    conversion_rate_bps: int # basis points e.g. 6500 = 65.0%
    average_ticket_minor: int
    projected_monthly_revenue_minor: int
    currency: str = "USD"


@dataclass
class TradeBreakdown:
    trade: str
    quotes_count: int
    accepted_count: int
    total_revenue_minor: int
    conversion_rate_bps: int


@dataclass
class CustomerLTV:
    customer_id: uuid.UUID
    customer_name: str
    total_quotes_count: int
    accepted_quotes_count: int
    lifetime_value_minor: int
    is_repeat_customer: bool


@dataclass
class QuoteEventRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    quote_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    event_type: str # quote.created, quote.sent, quote.accepted, quote.rejected
    trade: str # electrical, plumbing, hvac, general
    amount_minor: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
