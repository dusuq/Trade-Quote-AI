"""HTTP REST API routes for quote-service."""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Header, HTTPException, Query, status

from app.application import services
from app.application.services import (
    InvalidStatusTransitionError,
    LineItemNotFoundError,
    QuoteNotFoundError,
)
from app.config import settings
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


def _extract_auth_context(authorization: str) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Decodes JWT bearer token to extract (tenant_id, user_id)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Bearer token",
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        tenant_id = uuid.UUID(payload["tenant_id"])
        actor_id = uuid.UUID(payload["sub"]) if "sub" in payload else None
        return tenant_id, actor_id
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc


@router.post("", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
def create_quote(
    body: QuoteCreate,
    authorization: str = Header(default=""),
) -> QuoteResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
    with tenant_session(tenant_id) as session:
        quote, _event = services.create_quote(session, tenant_id, body, actor_id=actor_id)
        return QuoteResponse.model_validate(quote)


@router.get("", response_model=list[QuoteResponse])
def list_quotes(
    customer_id: uuid.UUID | None = Query(default=None, description="Filter by customer ID"),
    quote_status: QuoteStatus | None = Query(default=None, alias="status", description="Filter by quote status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str = Header(default=""),
) -> list[QuoteResponse]:
    tenant_id, _ = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> QuoteResponse:
    tenant_id, _ = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> QuoteResponse:
    tenant_id, _ = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> LineItemResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> LineItemResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> None:
    tenant_id, actor_id = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            services.delete_line_item(session, tenant_id, quote_id, line_item_id, actor_id=actor_id)
    except (QuoteNotFoundError, LineItemNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{quote_id}/send", response_model=QuoteResponse)
def send_quote(
    quote_id: uuid.UUID,
    body: QuoteSendRequest | None = None,
    authorization: str = Header(default=""),
) -> QuoteResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> QuoteResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> QuoteResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
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
    authorization: str = Header(default=""),
) -> list[QuoteVersionResponse]:
    tenant_id, _ = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            versions = services.list_quote_versions(session, tenant_id, quote_id)
            return [QuoteVersionResponse.model_validate(v) for v in versions]
    except QuoteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
