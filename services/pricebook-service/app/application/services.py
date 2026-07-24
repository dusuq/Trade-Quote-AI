"""Domain business logic and application services for the pricebook-service."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import ItemKind, PricebookItemModel, PricebookRegionPriceModel
from app.interface.schemas import (
    EffectivePriceResponse,
    PricebookItemCreate,
    PricebookItemUpdate,
)


class PricebookError(Exception):
    """Base exception for pricebook operations."""


class ItemNotFoundError(PricebookError):
    """Item not found."""


class DuplicateSKUError(PricebookError):
    """SKU code already exists within tenant."""


def create_event_envelope(
    event_name: str,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generates canonical domain event envelope matching @tradequote/types specification."""
    return {
        "eventId": str(uuid.uuid4()),
        "eventName": event_name,
        "eventVersion": 1,
        "tenantId": str(tenant_id),
        "actorId": str(actor_id) if actor_id else None,
        "occurredAt": datetime.now(UTC).isoformat(),
        "payload": payload,
    }


def create_item(
    session: Session,
    tenant_id: uuid.UUID,
    data: PricebookItemCreate,
    actor_id: uuid.UUID | None = None,
) -> tuple[PricebookItemModel, dict[str, Any]]:
    if data.sku:
        existing = session.scalar(
            select(PricebookItemModel).where(
                PricebookItemModel.tenant_id == tenant_id,
                PricebookItemModel.sku == data.sku,
            )
        )
        if existing:
            raise DuplicateSKUError(f"Item with SKU '{data.sku}' already exists.")

    item = PricebookItemModel(
        tenant_id=tenant_id,
        kind=data.kind,
        sku=data.sku,
        name=data.name,
        description=data.description,
        unit=data.unit,
        unit_cost_minor=data.unit_cost_minor,
        default_markup_bps=data.default_markup_bps,
        currency=data.currency,
        is_active=data.is_active,
    )
    session.add(item)
    session.flush()

    event = create_event_envelope(
        event_name="pricebook.item.upserted",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "itemId": str(item.id),
            "kind": item.kind.value,
            "sku": item.sku,
            "unitCost": {
                "amountMinor": item.unit_cost_minor,
                "currency": item.currency,
            },
        },
    )
    return item, event


def update_item(
    session: Session,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    data: PricebookItemUpdate,
    actor_id: uuid.UUID | None = None,
) -> tuple[PricebookItemModel, dict[str, Any]]:
    item = session.scalar(
        select(PricebookItemModel).where(
            PricebookItemModel.id == item_id,
            PricebookItemModel.tenant_id == tenant_id,
        )
    )
    if not item:
        raise ItemNotFoundError(f"Pricebook item '{item_id}' not found.")

    if data.sku and data.sku != item.sku:
        existing = session.scalar(
            select(PricebookItemModel).where(
                PricebookItemModel.tenant_id == tenant_id,
                PricebookItemModel.sku == data.sku,
                PricebookItemModel.id != item_id,
            )
        )
        if existing:
            raise DuplicateSKUError(f"Item with SKU '{data.sku}' already exists.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    session.flush()

    event = create_event_envelope(
        event_name="pricebook.item.upserted",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "itemId": str(item.id),
            "kind": item.kind.value,
            "sku": item.sku,
            "unitCost": {
                "amountMinor": item.unit_cost_minor,
                "currency": item.currency,
            },
        },
    )
    return item, event


def get_item(session: Session, tenant_id: uuid.UUID, item_id: uuid.UUID) -> PricebookItemModel:
    item = session.scalar(
        select(PricebookItemModel).where(
            PricebookItemModel.id == item_id,
            PricebookItemModel.tenant_id == tenant_id,
        )
    )
    if not item:
        raise ItemNotFoundError(f"Pricebook item '{item_id}' not found.")
    return item


def list_items(
    session: Session,
    tenant_id: uuid.UUID,
    kind: ItemKind | None = None,
    search: str | None = None,
    is_active: bool | None = True,
    skip: int = 0,
    limit: int = 100,
) -> list[PricebookItemModel]:
    stmt = select(PricebookItemModel).where(PricebookItemModel.tenant_id == tenant_id)
    if kind:
        stmt = stmt.where(PricebookItemModel.kind == kind)
    if is_active is not None:
        stmt = stmt.where(PricebookItemModel.is_active == is_active)
    if search:
        search_fmt = f"%{search}%"
        stmt = stmt.where(
            (PricebookItemModel.name.ilike(search_fmt))
            | (PricebookItemModel.sku.ilike(search_fmt))
            | (PricebookItemModel.description.ilike(search_fmt))
        )
    stmt = stmt.order_by(PricebookItemModel.name).offset(skip).limit(limit)
    return list(session.scalars(stmt).all())


def delete_item(session: Session, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item = get_item(session, tenant_id, item_id)
    item.is_active = False
    session.flush()


def set_region_price(
    session: Session,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    region_code: str,
    unit_cost_minor: int,
) -> PricebookRegionPriceModel:
    item = get_item(session, tenant_id, item_id)

    region_price = session.scalar(
        select(PricebookRegionPriceModel).where(
            PricebookRegionPriceModel.item_id == item_id,
            PricebookRegionPriceModel.region_code == region_code,
        )
    )
    if region_price:
        region_price.unit_cost_minor = unit_cost_minor
    else:
        region_price = PricebookRegionPriceModel(
            tenant_id=tenant_id,
            item_id=item.id,
            region_code=region_code,
            unit_cost_minor=unit_cost_minor,
        )
        session.add(region_price)

    session.flush()
    return region_price


def get_effective_price(
    session: Session,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    region_code: str | None = None,
) -> EffectivePriceResponse:
    item = get_item(session, tenant_id, item_id)

    cost_minor = item.unit_cost_minor
    applied_region = None

    if region_code:
        rp = session.scalar(
            select(PricebookRegionPriceModel).where(
                PricebookRegionPriceModel.item_id == item_id,
                PricebookRegionPriceModel.region_code == region_code,
            )
        )
        if rp:
            cost_minor = rp.unit_cost_minor
            applied_region = region_code

    markup_mult = 1.0 + (item.default_markup_bps / 10000.0)
    calc_price = round(cost_minor * markup_mult)

    return EffectivePriceResponse(
        item_id=item.id,
        name=item.name,
        sku=item.sku,
        unit=item.unit,
        currency=item.currency,
        region_code=applied_region,
        unit_cost_minor=cost_minor,
        default_markup_bps=item.default_markup_bps,
        calculated_price_minor=calc_price,
    )


def import_items_from_csv(
    session: Session,
    tenant_id: uuid.UUID,
    csv_text: str,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Imports items from a CSV string.
    Expected CSV columns: kind, name, sku, description, unit, unit_cost_minor, default_markup_bps, currency
    """
    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)

    total = 0
    created = 0
    updated = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        total += 1
        try:
            kind_str = (row.get("kind") or "material").strip().lower()
            name = (row.get("name") or "").strip()
            sku = (row.get("sku") or "").strip() or None
            description = (row.get("description") or "").strip() or None
            unit = (row.get("unit") or "each").strip()
            cost_minor = int(row.get("unit_cost_minor") or 0)
            markup_bps = int(row.get("default_markup_bps") or 0)
            currency = (row.get("currency") or "USD").strip().upper()

            if not name:
                errors.append(f"Row {row_num}: 'name' is required.")
                continue

            try:
                kind_enum = ItemKind(kind_str)
            except ValueError:
                errors.append(f"Row {row_num}: Invalid kind '{kind_str}'. Must be one of {[k.value for k in ItemKind]}.")
                continue

            existing = None
            if sku:
                existing = session.scalar(
                    select(PricebookItemModel).where(
                        PricebookItemModel.tenant_id == tenant_id,
                        PricebookItemModel.sku == sku,
                    )
                )

            if existing:
                existing.kind = kind_enum
                existing.name = name
                existing.description = description
                existing.unit = unit
                existing.unit_cost_minor = cost_minor
                existing.default_markup_bps = markup_bps
                existing.currency = currency
                existing.is_active = True
                updated += 1
            else:
                item_data = PricebookItemCreate(
                    kind=kind_enum,
                    sku=sku,
                    name=name,
                    description=description,
                    unit=unit,
                    unit_cost_minor=cost_minor,
                    default_markup_bps=markup_bps,
                    currency=currency,
                )
                create_item(session, tenant_id, item_data, actor_id=actor_id)
                created += 1

        except Exception as exc:  # noqa: BLE001 — bulk import must not abort on one bad row
            errors.append(f"Row {row_num}: {exc!s}")

    return {
        "total_rows": total,
        "created": created,
        "updated": updated,
        "errors": errors,
    }


from datetime import datetime
