"""Domain business logic, calculation engine, and services for the quote-service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    QuoteLineItemModel,
    QuoteModel,
    QuoteStatus,
    QuoteVersionModel,
)
from app.interface.schemas import (
    LineItemCreate,
    LineItemUpdate,
    QuoteCreate,
    QuoteUpdate,
)


class QuoteError(Exception):
    """Base exception for quote operations."""


class QuoteNotFoundError(QuoteError):
    """Quote not found."""


class LineItemNotFoundError(QuoteError):
    """Line item not found."""


class InvalidStatusTransitionError(QuoteError):
    """Invalid quote status transition."""


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


def generate_quote_number(session: Session, tenant_id: uuid.UUID) -> str:
    """Generates sequential quote number e.g. Q-2026-000001 per tenant."""
    year = datetime.now(UTC).year
    count = session.scalar(
        select(func.count(QuoteModel.id)).where(QuoteModel.tenant_id == tenant_id)
    ) or 0
    seq = count + 1
    return f"Q-{year}-{seq:06d}"


def calculate_unit_price(cost_minor: int, markup_bps: int) -> int:
    """Computes unit_price_minor from cost_minor and markup_bps (basis points)."""
    mult = 1.0 + (markup_bps / 10000.0)
    return round(cost_minor * mult)


def recalculate_quote_totals(session: Session, quote: QuoteModel) -> None:
    """Calculates line item totals, quote subtotal, tax, and grand total."""
    items = list(
        session.scalars(
            select(QuoteLineItemModel).where(QuoteLineItemModel.quote_id == quote.id)
        ).all()
    )
    subtotal = 0
    for line in items:
        # Calculate line item price and total
        line.line_total_minor = round(line.quantity * line.unit_price_minor)
        if not line.is_optional:
            subtotal += line.line_total_minor

    tax = round(subtotal * (quote.tax_rate_bps / 10000.0))
    total = subtotal + tax

    quote.subtotal_minor = subtotal
    quote.tax_minor = tax
    quote.total_minor = total
    session.flush()


def create_quote(
    session: Session,
    tenant_id: uuid.UUID,
    data: QuoteCreate,
    actor_id: uuid.UUID | None = None,
) -> tuple[QuoteModel, dict[str, Any]]:
    number = generate_quote_number(session, tenant_id)

    quote = QuoteModel(
        tenant_id=tenant_id,
        customer_id=data.customer_id,
        property_id=data.property_id,
        number=number,
        title=data.title,
        status=QuoteStatus.DRAFT,
        created_via=data.created_via,
        currency=data.currency,
        tax_rate_bps=data.tax_rate_bps,
        valid_until=data.valid_until,
        owner_id=data.owner_id,
    )
    session.add(quote)
    session.flush()

    for idx, item_in in enumerate(data.initial_line_items):
        unit_price = (
            item_in.unit_price_minor
            if item_in.unit_price_minor is not None
            else calculate_unit_price(item_in.unit_cost_minor, item_in.markup_bps)
        )
        line = QuoteLineItemModel(
            tenant_id=tenant_id,
            quote_id=quote.id,
            pricebook_item_id=item_in.pricebook_item_id,
            kind=item_in.kind,
            description=item_in.description,
            quantity=item_in.quantity,
            unit=item_in.unit,
            unit_cost_minor=item_in.unit_cost_minor,
            markup_bps=item_in.markup_bps,
            unit_price_minor=unit_price,
            is_optional=item_in.is_optional,
            sort_order=item_in.sort_order if item_in.sort_order else idx,
        )
        session.add(line)

    session.flush()
    recalculate_quote_totals(session, quote)

    event = create_event_envelope(
        event_name="quote.quote.created",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote.id),
            "customerId": str(quote.customer_id),
            "createdVia": quote.created_via.value,
        },
    )
    return quote, event


def get_quote(session: Session, tenant_id: uuid.UUID, quote_id: uuid.UUID) -> QuoteModel:
    quote = session.scalar(
        select(QuoteModel).where(
            QuoteModel.id == quote_id,
            QuoteModel.tenant_id == tenant_id,
        )
    )
    if not quote:
        raise QuoteNotFoundError(f"Quote '{quote_id}' not found.")
    return quote


def list_quotes(
    session: Session,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
    status: QuoteStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[QuoteModel]:
    stmt = select(QuoteModel).where(QuoteModel.tenant_id == tenant_id)
    if customer_id:
        stmt = stmt.where(QuoteModel.customer_id == customer_id)
    if status:
        stmt = stmt.where(QuoteModel.status == status)
    stmt = stmt.order_by(QuoteModel.created_at.desc()).offset(skip).limit(limit)
    return list(session.scalars(stmt).all())


def update_quote(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    data: QuoteUpdate,
) -> QuoteModel:
    quote = get_quote(session, tenant_id, quote_id)
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(quote, field, val)

    recalculate_quote_totals(session, quote)
    return quote


def add_line_item(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    data: LineItemCreate,
    actor_id: uuid.UUID | None = None,
) -> tuple[QuoteLineItemModel, dict[str, Any]]:
    quote = get_quote(session, tenant_id, quote_id)

    unit_price = (
        data.unit_price_minor
        if data.unit_price_minor is not None
        else calculate_unit_price(data.unit_cost_minor, data.markup_bps)
    )
    line = QuoteLineItemModel(
        tenant_id=tenant_id,
        quote_id=quote.id,
        pricebook_item_id=data.pricebook_item_id,
        kind=data.kind,
        description=data.description,
        quantity=data.quantity,
        unit=data.unit,
        unit_cost_minor=data.unit_cost_minor,
        markup_bps=data.markup_bps,
        unit_price_minor=unit_price,
        is_optional=data.is_optional,
        sort_order=data.sort_order,
    )
    session.add(line)
    session.flush()

    recalculate_quote_totals(session, quote)

    event = create_event_envelope(
        event_name="quote.quote.lineItemsChanged",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote.id),
            "lineItemCount": len(quote.line_items),
            "subtotal": {
                "amountMinor": quote.subtotal_minor,
                "currency": quote.currency,
            },
        },
    )
    return line, event


def update_line_item(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    line_item_id: uuid.UUID,
    data: LineItemUpdate,
    actor_id: uuid.UUID | None = None,
) -> tuple[QuoteLineItemModel, dict[str, Any]]:
    quote = get_quote(session, tenant_id, quote_id)
    line = session.scalar(
        select(QuoteLineItemModel).where(
            QuoteLineItemModel.id == line_item_id,
            QuoteLineItemModel.quote_id == quote_id,
            QuoteLineItemModel.tenant_id == tenant_id,
        )
    )
    if not line:
        raise LineItemNotFoundError(f"Line item '{line_item_id}' not found.")

    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(line, field, val)

    # Re-calculate unit price if cost or markup changed without explicit unit_price_minor override
    if ("unit_cost_minor" in data.model_dump(exclude_unset=True) or "markup_bps" in data.model_dump(exclude_unset=True)) and data.unit_price_minor is None:
        line.unit_price_minor = calculate_unit_price(line.unit_cost_minor, line.markup_bps)

    session.flush()
    recalculate_quote_totals(session, quote)

    event = create_event_envelope(
        event_name="quote.quote.lineItemsChanged",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote.id),
            "lineItemCount": len(quote.line_items),
            "subtotal": {
                "amountMinor": quote.subtotal_minor,
                "currency": quote.currency,
            },
        },
    )
    return line, event


def delete_line_item(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    line_item_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    quote = get_quote(session, tenant_id, quote_id)
    line = session.scalar(
        select(QuoteLineItemModel).where(
            QuoteLineItemModel.id == line_item_id,
            QuoteLineItemModel.quote_id == quote_id,
            QuoteLineItemModel.tenant_id == tenant_id,
        )
    )
    if not line:
        raise LineItemNotFoundError(f"Line item '{line_item_id}' not found.")

    session.delete(line)
    session.flush()

    recalculate_quote_totals(session, quote)

    event = create_event_envelope(
        event_name="quote.quote.lineItemsChanged",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote.id),
            "lineItemCount": len(quote.line_items),
            "subtotal": {
                "amountMinor": quote.subtotal_minor,
                "currency": quote.currency,
            },
        },
    )
    return event


def create_version_snapshot(quote: QuoteModel) -> dict[str, Any]:
    """Generates full dictionary snapshot of quote + line items."""
    return {
        "id": str(quote.id),
        "number": quote.number,
        "title": quote.title,
        "status": quote.status.value,
        "currency": quote.currency,
        "tax_rate_bps": quote.tax_rate_bps,
        "subtotal_minor": quote.subtotal_minor,
        "tax_minor": quote.tax_minor,
        "total_minor": quote.total_minor,
        "version": quote.current_version,
        "created_at": quote.created_at.isoformat(),
        "line_items": [
            {
                "id": str(line.id),
                "kind": line.kind.value,
                "description": line.description,
                "quantity": float(line.quantity),
                "unit": line.unit,
                "unit_cost_minor": line.unit_cost_minor,
                "markup_bps": line.markup_bps,
                "unit_price_minor": line.unit_price_minor,
                "line_total_minor": line.line_total_minor,
                "is_optional": line.is_optional,
            }
            for line in quote.line_items
        ],
    }


def send_quote(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    channel: str = "email",
    actor_id: uuid.UUID | None = None,
) -> tuple[QuoteModel, dict[str, Any]]:
    quote = get_quote(session, tenant_id, quote_id)
    recalculate_quote_totals(session, quote)

    quote.status = QuoteStatus.SENT

    # Create immutable version snapshot
    snapshot = create_version_snapshot(quote)
    version = QuoteVersionModel(
        tenant_id=tenant_id,
        quote_id=quote.id,
        version=quote.current_version,
        snapshot=snapshot,
    )
    session.add(version)

    # Increment current_version for next edit iteration
    quote.current_version += 1
    session.flush()

    event = create_event_envelope(
        event_name="quote.quote.sent",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote.id),
            "channel": channel,
        },
    )
    return quote, event


def accept_quote(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> tuple[QuoteModel, dict[str, Any]]:
    quote = get_quote(session, tenant_id, quote_id)
    if quote.status in (QuoteStatus.EXPIRED, QuoteStatus.ARCHIVED):
        raise InvalidStatusTransitionError(f"Cannot accept quote in '{quote.status.value}' state.")

    quote.status = QuoteStatus.ACCEPTED
    session.flush()

    event = create_event_envelope(
        event_name="quote.estimate.accepted",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote.id),
            "total": {
                "amountMinor": quote.total_minor,
                "currency": quote.currency,
            },
            "acceptedAt": datetime.now(UTC).isoformat(),
        },
    )
    return quote, event


def reject_quote(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    reason: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> tuple[QuoteModel, dict[str, Any]]:
    quote = get_quote(session, tenant_id, quote_id)
    if quote.status in (QuoteStatus.EXPIRED, QuoteStatus.ARCHIVED):
        raise InvalidStatusTransitionError(f"Cannot reject quote in '{quote.status.value}' state.")

    quote.status = QuoteStatus.REJECTED
    session.flush()

    event = create_event_envelope(
        event_name="quote.estimate.rejected",
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload={
            "quoteId": str(quote.id),
            "reason": reason,
        },
    )
    return quote, event


def list_quote_versions(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
) -> list[QuoteVersionModel]:
    get_quote(session, tenant_id, quote_id)
    stmt = (
        select(QuoteVersionModel)
        .where(
            QuoteVersionModel.quote_id == quote_id,
            QuoteVersionModel.tenant_id == tenant_id,
        )
        .order_by(QuoteVersionModel.version.asc())
    )
    return list(session.scalars(stmt).all())
