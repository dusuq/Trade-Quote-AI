"""Margin and markup arithmetic for the copilot.

Pure functions — no I/O, no framework, no LLM. This is a deliberate design
decision (M16 plan §Key Design Decisions #2): asking an LLM to do money math
and trusting the result would be wrong, so the numbers come from the quote's
own data and the model only supplies the *reasoning*.

Everything here stays in integer minor units and basis points (conventions
§5). Line cost is the one place a `Decimal` quantity meets a money value; it is
quantized back to whole minor units with `ROUND_HALF_UP` so no fractional cent
escapes.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.domain.models import MarginAnalysis, QuoteLineItem, QuoteSnapshot

# A line earning less than 20% gross margin is flagged. 20% is a common floor
# once a contractor's overhead (truck, insurance, admin) is accounted for —
# below it a job can lose money even though the invoice looks profitable.
LOW_MARGIN_THRESHOLD_BPS = 2000

_BPS = 10_000


def _round_minor(value: Decimal) -> int:
    """Round a Decimal money value to whole minor units, half up."""
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def line_cost_minor(item: QuoteLineItem) -> int:
    """Extended cost of a line: unit cost × quantity, in whole minor units."""
    return _round_minor(Decimal(item.unit_cost_minor) * item.quantity)


def margin_bps(revenue_minor: int, cost_minor: int) -> int:
    """Gross margin in basis points: (revenue - cost) / revenue.

    Zero (not an error) when there is no revenue — a $0 line has no margin to
    speak of, and dividing by zero to say so would just crash the analysis.
    """
    if revenue_minor <= 0:
        return 0
    return round((revenue_minor - cost_minor) * _BPS / revenue_minor)


def markup_bps(revenue_minor: int, cost_minor: int) -> int:
    """Markup in basis points: (revenue - cost) / cost.

    Zero when there is no cost — you cannot mark up nothing.
    """
    if cost_minor <= 0:
        return 0
    return round((revenue_minor - cost_minor) * _BPS / cost_minor)


def low_margin_item_ids(
    quote: QuoteSnapshot, *, threshold_bps: int = LOW_MARGIN_THRESHOLD_BPS
) -> tuple[UUID, ...]:
    """Ids of lines whose gross margin is below `threshold_bps`.

    A line's revenue is its `line_total_minor` (unit price × quantity, already
    computed by quote-service); its cost is `unit_cost_minor × quantity`.
    """
    flagged: list[UUID] = []
    for item in quote.line_items:
        if margin_bps(item.line_total_minor, line_cost_minor(item)) < threshold_bps:
            flagged.append(item.id)
    return tuple(flagged)


def compute_margin(quote: QuoteSnapshot, recommendation: str) -> MarginAnalysis:
    """Build the quote-level margin summary from raw numbers + LLM prose.

    `total_revenue_minor` is the quote's subtotal (excludes tax) rather than a
    re-sum of the lines, so it stays consistent with what quote-service itself
    reports as the pre-tax total.
    """
    total_cost = sum(line_cost_minor(item) for item in quote.line_items)
    total_revenue = quote.subtotal_minor
    return MarginAnalysis(
        total_cost_minor=total_cost,
        total_revenue_minor=total_revenue,
        gross_margin_bps=margin_bps(total_revenue, total_cost),
        average_markup_bps=markup_bps(total_revenue, total_cost),
        low_margin_item_ids=low_margin_item_ids(quote),
        recommendation=recommendation,
    )
