"""HTTP REST API routes for pricebook-service."""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile, status

from app.application import services
from app.application.services import DuplicateSKUError, ItemNotFoundError
from app.config import settings
from app.domain.models import ItemKind
from app.domain.schemas import (
    EffectivePriceResponse,
    PricebookImportSummary,
    PricebookItemCreate,
    PricebookItemResponse,
    PricebookItemUpdate,
    PricebookRegionPriceCreate,
    PricebookRegionPriceResponse,
)
from app.infrastructure.db import tenant_session

router = APIRouter(prefix="/v1/pricebook", tags=["pricebook"])


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


@router.post("/items", response_model=PricebookItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    body: PricebookItemCreate,
    authorization: str = Header(default=""),
) -> PricebookItemResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            item, _event = services.create_item(session, tenant_id, body, actor_id=actor_id)
            return PricebookItemResponse.model_validate(item)
    except DuplicateSKUError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/items", response_model=list[PricebookItemResponse])
def list_items(
    kind: ItemKind | None = Query(default=None, description="Filter by item kind"),
    search: str | None = Query(default=None, description="Search term for name, sku, or description"),
    is_active: bool | None = Query(default=True, description="Filter active/inactive status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str = Header(default=""),
) -> list[PricebookItemResponse]:
    tenant_id, _ = _extract_auth_context(authorization)
    with tenant_session(tenant_id) as session:
        items = services.list_items(
            session,
            tenant_id=tenant_id,
            kind=kind,
            search=search,
            is_active=is_active,
            skip=skip,
            limit=limit,
        )
        return [PricebookItemResponse.model_validate(item) for item in items]


@router.get("/items/{item_id}", response_model=PricebookItemResponse)
def get_item(
    item_id: uuid.UUID,
    authorization: str = Header(default=""),
) -> PricebookItemResponse:
    tenant_id, _ = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            item = services.get_item(session, tenant_id, item_id)
            return PricebookItemResponse.model_validate(item)
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/items/{item_id}", response_model=PricebookItemResponse)
def update_item(
    item_id: uuid.UUID,
    body: PricebookItemUpdate,
    authorization: str = Header(default=""),
) -> PricebookItemResponse:
    tenant_id, actor_id = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            item, _event = services.update_item(session, tenant_id, item_id, body, actor_id=actor_id)
            return PricebookItemResponse.model_validate(item)
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateSKUError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: uuid.UUID,
    authorization: str = Header(default=""),
) -> None:
    tenant_id, _ = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            services.delete_item(session, tenant_id, item_id)
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/items/{item_id}/region-prices", response_model=PricebookRegionPriceResponse)
def set_region_price(
    item_id: uuid.UUID,
    body: PricebookRegionPriceCreate,
    authorization: str = Header(default=""),
) -> PricebookRegionPriceResponse:
    tenant_id, _ = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            rp = services.set_region_price(
                session,
                tenant_id=tenant_id,
                item_id=item_id,
                region_code=body.region_code,
                unit_cost_minor=body.unit_cost_minor,
            )
            return PricebookRegionPriceResponse.model_validate(rp)
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/items/{item_id}/effective-price", response_model=EffectivePriceResponse)
def get_effective_price(
    item_id: uuid.UUID,
    region_code: str | None = Query(default=None, description="Optional region code e.g. US-CA"),
    authorization: str = Header(default=""),
) -> EffectivePriceResponse:
    tenant_id, _ = _extract_auth_context(authorization)
    try:
        with tenant_session(tenant_id) as session:
            return services.get_effective_price(
                session,
                tenant_id=tenant_id,
                item_id=item_id,
                region_code=region_code,
            )
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/import", response_model=PricebookImportSummary)

async def import_csv(
    file: UploadFile = File(...),
    authorization: str = Header(default=""),
) -> PricebookImportSummary:
    tenant_id, actor_id = _extract_auth_context(authorization)
    contents = await file.read()
    csv_text = contents.decode("utf-8")
    with tenant_session(tenant_id) as session:
        result = services.import_items_from_csv(
            session,
            tenant_id=tenant_id,
            csv_text=csv_text,
            actor_id=actor_id,
        )
        return PricebookImportSummary(**result)
