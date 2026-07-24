"""HTTP REST API routes for pricebook-service.

Trusts the API Gateway's identity headers (x-tenant-id, x-user-id) — the gateway already
verified the JWT (see apps/api-gateway), so this service never decodes tokens itself.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile, status

from app.application import services
from app.application.services import DuplicateSKUError, ItemNotFoundError
from app.domain.models import ItemKind
from app.infrastructure.db import tenant_session
from app.interface.schemas import (
    EffectivePriceResponse,
    PricebookImportSummary,
    PricebookItemCreate,
    PricebookItemResponse,
    PricebookItemUpdate,
    PricebookRegionPriceCreate,
    PricebookRegionPriceResponse,
)

router = APIRouter(prefix="/v1/pricebook", tags=["pricebook"])


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


@router.post("/items", response_model=PricebookItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    body: PricebookItemCreate,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PricebookItemResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
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
    x_tenant_id: str | None = Header(default=None),
) -> list[PricebookItemResponse]:
    tenant_id = _require_tenant(x_tenant_id)
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
    x_tenant_id: str | None = Header(default=None),
) -> PricebookItemResponse:
    tenant_id = _require_tenant(x_tenant_id)
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
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PricebookItemResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
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
    x_tenant_id: str | None = Header(default=None),
) -> None:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            services.delete_item(session, tenant_id, item_id)
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/items/{item_id}/region-prices", response_model=PricebookRegionPriceResponse)
def set_region_price(
    item_id: uuid.UUID,
    body: PricebookRegionPriceCreate,
    x_tenant_id: str | None = Header(default=None),
) -> PricebookRegionPriceResponse:
    tenant_id = _require_tenant(x_tenant_id)
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
    x_tenant_id: str | None = Header(default=None),
) -> EffectivePriceResponse:
    tenant_id = _require_tenant(x_tenant_id)
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
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PricebookImportSummary:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _require_user(x_user_id)
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
