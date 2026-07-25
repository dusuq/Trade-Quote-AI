import uuid

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.application.services import AnalyticsService
from app.infrastructure.repositories import InMemoryAnalyticsRepository
from app.interface.schemas import (
    AnalyticsOverviewResponse,
    CustomerLTVResponse,
    IngestQuoteEventRequest,
    IngestQuoteEventResponse,
    TradeBreakdownResponse,
)

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

# Shared in-memory instance for stateless execution/testing
shared_repo = InMemoryAnalyticsRepository()


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    """Trusts x-tenant-id header forwarded from API Gateway per docs/07-SERVICE-CONVENTIONS.md."""
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required x-tenant-id header from API Gateway",
        )
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid x-tenant-id header UUID format",
        ) from None


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    x_tenant_id: str | None = Header(None, alias="x-tenant-id"),
) -> AnalyticsOverviewResponse:
    tenant_id = _require_tenant(x_tenant_id)
    service = AnalyticsService(shared_repo)
    overview = service.get_overview(tenant_id)
    return AnalyticsOverviewResponse.model_validate(overview)


@router.get("/trades", response_model=list[TradeBreakdownResponse])
def get_trade_breakdowns(
    x_tenant_id: str | None = Header(None, alias="x-tenant-id"),
) -> list[TradeBreakdownResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    service = AnalyticsService(shared_repo)
    breakdowns = service.get_trade_breakdowns(tenant_id)
    return [TradeBreakdownResponse.model_validate(b) for b in breakdowns]


@router.get("/customers", response_model=list[CustomerLTVResponse])
def get_customer_ltv(
    x_tenant_id: str | None = Header(None, alias="x-tenant-id"),
    limit: int = Query(10, ge=1, le=100),
) -> list[CustomerLTVResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    service = AnalyticsService(shared_repo)
    ltv_list = service.get_customer_ltv(tenant_id, limit=limit)
    return [CustomerLTVResponse.model_validate(item) for item in ltv_list]


@router.post(
    "/events/ingest",
    response_model=IngestQuoteEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_quote_event(
    body: IngestQuoteEventRequest,
    x_tenant_id: str | None = Header(None, alias="x-tenant-id"),
) -> IngestQuoteEventResponse:
    tenant_id = _require_tenant(x_tenant_id)
    service = AnalyticsService(shared_repo)
    record = service.ingest_quote_event(
        tenant_id=tenant_id,
        quote_id=body.quote_id,
        customer_id=body.customer_id,
        customer_name=body.customer_name,
        event_type=body.event_type,
        trade=body.trade,
        amount_minor=body.amount_minor,
    )
    return IngestQuoteEventResponse(
        event_id=record.id,
        quote_id=record.quote_id,
        event_type=record.event_type,
    )
