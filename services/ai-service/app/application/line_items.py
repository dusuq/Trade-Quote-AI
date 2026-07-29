"""Turning matched tasks into quote-service line items.

Pure functions — no I/O, no framework. This is where the money conventions
(§5) are enforced, so it is worth reading closely and is heavily tested.

**This module deliberately does not compute prices.** `quote-service`'s
`LineItemCreate.unit_price_minor` is documented as derived from
`unit_cost_minor * (1 + markup_bps/10000)` when omitted, so we send cost and
markup and let quote-service remain the single source of truth for pricing.
Recomputing it here would create a second implementation that can drift.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domain.models import LineItemDraft, MatchedTask

# 30% — a common contractor default, and the same value the API surface
# advertises. Callers override per request.
DEFAULT_MARKUP_BPS = 3000


def normalize_quantity(value: object) -> Decimal:
    """Coerce an inbound quantity to `Decimal` without passing through binary float.

    `Decimal(0.1)` is 0.1000000000000000055511151231257827; `Decimal("0.1")`
    is exactly 0.1. Quantities multiply money, so the difference is a real
    (if small) pricing error — always go via `str`.
    """
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"quantity {value!r} is not a number") from exc

    if not quantity.is_finite():
        raise ValueError(f"quantity {value!r} is not finite")
    if quantity <= 0:
        raise ValueError(f"quantity must be greater than zero, got {quantity}")
    return quantity


def to_line_item(
    matched: MatchedTask, *, default_markup_bps: int = DEFAULT_MARKUP_BPS, sort_order: int = 0
) -> LineItemDraft:
    """Build one line item from a task and (optionally) its pricebook match."""
    if default_markup_bps < 0:
        raise ValueError("markup_bps must be non-negative")

    task = matched.task
    match = matched.match

    if match is None:
        # No pricebook hit. Carry the scope through at zero cost so the
        # contractor sees and prices it, rather than silently dropping work
        # the customer actually described. Markup is 0 rather than the
        # default: marking up nothing is still nothing, and a non-zero markup
        # here would imply we priced something we didn't.
        return LineItemDraft(
            description=task.description,
            kind=task.category.value,
            quantity=task.quantity,
            unit=task.unit,
            unit_cost_minor=0,
            markup_bps=0,
            pricebook_item_id=None,
            sort_order=sort_order,
        )

    # Matched: prefer the pricebook's own `kind`, `unit`, and markup over the
    # LLM's guess and the request-level default. The catalog is authoritative
    # about what an item *is*, how it is sold, and what this tenant marks it
    # up by; the model only found it.
    return LineItemDraft(
        description=task.description,
        kind=match.kind,
        quantity=task.quantity,
        unit=match.unit or task.unit,
        unit_cost_minor=match.unit_cost_minor,
        markup_bps=(
            match.default_markup_bps if match.default_markup_bps > 0 else default_markup_bps
        ),
        pricebook_item_id=match.pricebook_item_id,
        sort_order=sort_order,
    )


def build_line_items(
    matched_tasks: list[MatchedTask], *, default_markup_bps: int = DEFAULT_MARKUP_BPS
) -> list[LineItemDraft]:
    """Map every matched task to a line item, preserving order."""
    return [
        to_line_item(matched, default_markup_bps=default_markup_bps, sort_order=index)
        for index, matched in enumerate(matched_tasks)
    ]
