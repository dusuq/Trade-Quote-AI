"""HTTP REST API routes for quote-service.

Trusts the API Gateway's identity headers (x-tenant-id, x-user-id) — the gateway already
verified the JWT (see apps/api-gateway), so this service never decodes tokens itself.
"""

from __future__ import annotations

import uuid
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status

from app.application import services
from app.application.services import (
    InvalidStatusTransitionError,
    LineItemNotFoundError,
    QuoteNotFoundError,
)
from app.application.summary import InvalidTimezoneError, resolve_range, summarize_quotes
from app.config import settings
from app.domain.models import QuoteStatus
from app.domain.trade_inference import infer_trade
from app.infrastructure.db import tenant_session
from app.interface.schemas import (
    CurrencyTotalResponse,
    LineItemCreate,
    LineItemResponse,
    LineItemUpdate,
    QuoteCreate,
    QuoteRejectRequest,
    QuoteResponse,
    QuoteSendRequest,
    QuoteSummaryResponse,
    QuoteUpdate,
    QuoteVersionResponse,
)

router = APIRouter(prefix="/v1/quotes", tags=["quotes"])


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _require_user(x_user_id: str | None) -> uuid.UUID | None:
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return None


def _emit_analytics_event(
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    customer_id: uuid.UUID,
    event_type: str,
    trade: str,
    amount_minor: int,
    customer_name: str | None = None,
) -> None:
    """Best-effort background HTTP dispatch of quote domain events to analytics-service ingest endpoint.
    
    Executes outside database transactions and catches all exceptions to ensure analytics I/O failures
    never interfere with quote mutations.
    """
    try:
        url = f"{settings.analytics_service_url.rstrip('/')}/v1/analytics/events/ingest"
        payload = {
            "quote_id": str(quote_id),
            "customer_id": str(customer_id),
            "customer_name": customer_name,
            "event_type": event_type,
            "trade": trade,
            "amount_minor": amount_minor,
        }
        headers = {"x-tenant-id": str(tenant_id), "content-type": "application/json"}
        httpx.post(url, json=payload, headers=headers, timeout=3.0)
    except Exception:  # noqa: BLE001
        return


@router.post("", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
def create_quote(
    body: QuoteCreate,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    with tenant_session(tenant_id) as session:
        quote, _event = services.create_quote(session, tenant_id, body, actor_id=actor_id)
        quote_resp = QuoteResponse.model_validate(quote)

    trade = infer_trade(quote.title)
    background_tasks.add_task(
        _emit_analytics_event,
        tenant_id=tenant_id,
        quote_id=quote.id,
        customer_id=quote.customer_id,
        event_type="quote.quote.created",
        trade=trade,
        amount_minor=quote.total_minor,
    )
    return quote_resp


@router.get("", response_model=list[QuoteResponse])
def list_quotes(
    customer_id: uuid.UUID | None = Query(default=None, description="Filter by customer ID"),
    quote_status: QuoteStatus | None = Query(default=None, alias="status", description="Filter by quote status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    x_tenant_id: str | None = Header(default=None),
) -> list[QuoteResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        quotes = services.list_quotes(
            session,
            tenant_id=tenant_id,
            customer_id=customer_id,
            status=quote_status,
            skip=skip,
            limit=limit,
        )
        return [QuoteResponse.model_validate(q) for q in quotes]


@router.get("/summary", response_model=QuoteSummaryResponse)
def get_quotes_summary(
    tz: str | None = Query(default=None, description="IANA timezone, e.g. Australia/Sydney"),
    range_key: Literal["mtd", "ytd"] = Query(default="mtd", alias="range"),
    x_tenant_id: str | None = Header(default=None),
) -> QuoteSummaryResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        bounds = resolve_range(tz, range_key)
    except InvalidTimezoneError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    with tenant_session(tenant_id) as session:
        summary = summarize_quotes(session, tenant_id, bounds)
        return QuoteSummaryResponse(
            timezone=summary.bounds.timezone,
            range=range_key,
            range_start=summary.bounds.range_start,
            range_end=summary.bounds.range_end,
            quotes_today=summary.quotes_today,
            pending_count=summary.pending_count,
            accepted_count=summary.accepted_count,
            decided_count=summary.decided_count,
            conversion_bps=summary.conversion_bps,
            totals=[
                CurrencyTotalResponse(currency=t.currency, accepted_value_minor=t.accepted_value_minor)
                for t in summary.totals
            ],
        )


@router.get("/{quote_id}", response_model=QuoteResponse)
def get_quote(
    quote_id: uuid.UUID,
    x_tenant_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            quote = services.get_quote(session, tenant_id, quote_id)
            return QuoteResponse.model_validate(quote)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{quote_id}", response_model=QuoteResponse)
def update_quote(
    quote_id: uuid.UUID,
    body: QuoteUpdate,
    x_tenant_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            quote = services.update_quote(session, tenant_id, quote_id, body)
            return QuoteResponse.model_validate(quote)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{quote_id}/line-items", response_model=LineItemResponse, status_code=status.HTTP_201_CREATED)
def add_line_item(
    quote_id: uuid.UUID,
    body: LineItemCreate,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> LineItemResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    try:
        with tenant_session(tenant_id) as session:
            line, _event = services.add_line_item(session, tenant_id, quote_id, body, actor_id=actor_id)
            return LineItemResponse.model_validate(line)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{quote_id}/line-items/{line_item_id}", response_model=LineItemResponse)
def update_line_item(
    quote_id: uuid.UUID,
    line_item_id: uuid.UUID,
    body: LineItemUpdate,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> LineItemResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    try:
        with tenant_session(tenant_id) as session:
            line, _event = services.update_line_item(
                session, tenant_id, quote_id, line_item_id, body, actor_id=actor_id
            )
            return LineItemResponse.model_validate(line)
    except (QuoteNotFoundError, LineItemNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{quote_id}/line-items/{line_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line_item(
    quote_id: uuid.UUID,
    line_item_id: uuid.UUID,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> None:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    try:
        with tenant_session(tenant_id) as session:
            services.delete_line_item(session, tenant_id, quote_id, line_item_id, actor_id=actor_id)
    except (QuoteNotFoundError, LineItemNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{quote_id}/send", response_model=QuoteResponse)
def send_quote(
    quote_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    body: QuoteSendRequest | None = None,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    channel = body.channel if body else "email"
    try:
        with tenant_session(tenant_id) as session:
            quote, _event = services.send_quote(
                session, tenant_id, quote_id, channel=channel, actor_id=actor_id
            )
            quote_resp = QuoteResponse.model_validate(quote)
            trade = infer_trade(quote.title, [item.description for item in quote.line_items])
            bg_args = (tenant_id, quote.id, quote.customer_id, "quote.quote.sent", trade, quote.total_minor)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    background_tasks.add_task(_emit_analytics_event, *bg_args)
    return quote_resp


@router.post("/{quote_id}/accept", response_model=QuoteResponse)
def accept_quote(
    quote_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    try:
        with tenant_session(tenant_id) as session:
            quote, _event = services.accept_quote(session, tenant_id, quote_id, actor_id=actor_id)
            quote_resp = QuoteResponse.model_validate(quote)
            trade = infer_trade(quote.title, [item.description for item in quote.line_items])
            bg_args = (tenant_id, quote.id, quote.customer_id, "quote.estimate.accepted", trade, quote.total_minor)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    background_tasks.add_task(_emit_analytics_event, *bg_args)
    return quote_resp


@router.post("/{quote_id}/reject", response_model=QuoteResponse)
def reject_quote(
    quote_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    body: QuoteRejectRequest | None = None,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    reason = body.reason if body else None
    try:
        with tenant_session(tenant_id) as session:
            quote, _event = services.reject_quote(
                session, tenant_id, quote_id, reason=reason, actor_id=actor_id
            )
            quote_resp = QuoteResponse.model_validate(quote)
            trade = infer_trade(quote.title, [item.description for item in quote.line_items])
            bg_args = (tenant_id, quote.id, quote.customer_id, "quote.estimate.rejected", trade, quote.total_minor)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    background_tasks.add_task(_emit_analytics_event, *bg_args)
    return quote_resp


@router.get("/{quote_id}/versions", response_model=list[QuoteVersionResponse])
def list_versions(
    quote_id: uuid.UUID,
    x_tenant_id: str | None = Header(default=None),
) -> list[QuoteVersionResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            versions = services.list_quote_versions(session, tenant_id, quote_id)
            return [QuoteVersionResponse.model_validate(v) for v in versions]
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
