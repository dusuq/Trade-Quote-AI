"""HTTP REST API routes for quote-service.

Trusts the API Gateway's identity headers (x-tenant-id, x-user-id) — the gateway already
verified the JWT (see apps/api-gateway), so this service never decodes tokens itself.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.application import services
from app.application.services import (
    InvalidStatusTransitionError,
    LineItemNotFoundError,
    QuoteNotFoundError,
)
from app.domain.models import QuoteStatus
from app.domain.schemas import (
    LineItemCreate,
    LineItemResponse,
    LineItemUpdate,
    QuoteCreate,
    QuoteRejectRequest,
    QuoteResponse,
    QuoteSendRequest,
    QuoteUpdate,
    QuoteVersionResponse,
)
from app.infrastructure.db import tenant_session

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


@router.post("", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
def create_quote(
    body: QuoteCreate,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    with tenant_session(tenant_id) as session:
        quote, _event = services.create_quote(session, tenant_id, body, actor_id=actor_id)
        return QuoteResponse.model_validate(quote)


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
            return QuoteResponse.model_validate(quote)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{quote_id}/accept", response_model=QuoteResponse)
def accept_quote(
    quote_id: uuid.UUID,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
    try:
        with tenant_session(tenant_id) as session:
            quote, _event = services.accept_quote(session, tenant_id, quote_id, actor_id=actor_id)
            return QuoteResponse.model_validate(quote)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{quote_id}/reject", response_model=QuoteResponse)
def reject_quote(
    quote_id: uuid.UUID,
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
            return QuoteResponse.model_validate(quote)
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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
