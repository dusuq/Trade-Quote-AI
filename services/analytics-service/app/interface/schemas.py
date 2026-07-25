import uuid

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsOverviewResponse(BaseModel):
    tenant_id: uuid.UUID
    total_quotes_count: int
    draft_count: int
    sent_count: int
    accepted_count: int
    rejected_count: int
    total_accepted_value_minor: int
    total_pipeline_value_minor: int
    conversion_rate_bps: int
    average_ticket_minor: int
    projected_monthly_revenue_minor: int
    currency: str = "USD"

    model_config = ConfigDict(from_attributes=True)


class TradeBreakdownResponse(BaseModel):
    trade: str
    quotes_count: int
    accepted_count: int
    total_revenue_minor: int
    conversion_rate_bps: int

    model_config = ConfigDict(from_attributes=True)


class CustomerLTVResponse(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    total_quotes_count: int
    accepted_quotes_count: int
    lifetime_value_minor: int
    is_repeat_customer: bool

    model_config = ConfigDict(from_attributes=True)


class IngestQuoteEventRequest(BaseModel):
    quote_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    event_type: str = Field(
        ..., description="quote.created, quote.sent, quote.accepted, quote.rejected"
    )
    trade: str = Field(..., description="electrical, plumbing, hvac, general")
    amount_minor: int = Field(..., ge=0, description="Amount in minor units (cents)")


class IngestQuoteEventResponse(BaseModel):
    status: str = "recorded"
    event_id: uuid.UUID
    quote_id: uuid.UUID
    event_type: str
