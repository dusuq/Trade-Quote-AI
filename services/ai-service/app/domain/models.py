"""Domain entities for the AI Quote Assistant (M15 / T201).

Framework-free — no SQLAlchemy, no Pydantic, no SDK types (conventions §3).

Money is integer minor units; rates are basis points (conventions §5).
Quantities are `Decimal`, never `float`: a quantity multiplies a money value,
so a binary-float quantity would leak rounding error straight into a price.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID


class Trade(str, enum.Enum):
    """Trade taxonomy the extractor must classify into.

    Deliberately a closed set: M21's "profit by trade" breakdown is only
    meaningful if every quote lands in one of a fixed number of buckets.
    (T307b's version derived `trade` from free text, which produced one
    bucket per quote — see that audit.)
    """

    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    HVAC = "hvac"
    SOLAR = "solar"
    ROOFING = "roofing"
    FLOORING = "flooring"
    LANDSCAPING = "landscaping"
    PAINTING = "painting"
    CLEANING = "cleaning"
    GENERAL = "general"


class TaskCategory(str, enum.Enum):
    """Maps 1:1 onto quote-service's `ItemKind` for the three kinds the
    extractor can produce."""

    MATERIAL = "material"
    LABOR = "labor"
    EQUIPMENT = "equipment"


class InputKind(str, enum.Enum):
    """Mirrors `AiQuoteDraftedPayload.inputKind` in packages/types."""

    VOICE = "voice"
    TEXT = "text"


class AiFeature(str, enum.Enum):
    """Mirrors `AiUsageRecordedPayload.feature` in packages/types."""

    VOICE = "voice"
    SCOPE_WRITER = "scope_writer"


@dataclass(slots=True, frozen=True)
class TranscriptionResult:
    """Raw speech-to-text output."""

    text: str
    language: str
    duration_seconds: float
    model_id: str


@dataclass(slots=True, frozen=True)
class ExtractedTask:
    """One billable line item the LLM found in the job description."""

    description: str
    category: TaskCategory
    item_name: str
    quantity: Decimal
    unit: str


@dataclass(slots=True, frozen=True)
class ExtractedScope:
    """Structured scope extracted from a job description."""

    trade: Trade
    summary: str
    tasks: tuple[ExtractedTask, ...]
    notes: str = ""


@dataclass(slots=True, frozen=True)
class PricebookMatch:
    """A pricebook item matched to an extracted task.

    `confidence` is 0.0–1.0. It is advisory metadata for the UI — it never
    silently changes a price.
    """

    pricebook_item_id: UUID
    name: str
    kind: str
    unit_cost_minor: int
    unit: str
    confidence: float
    # The catalog's own markup for this item. Preferred over the request-level
    # default when set — a tenant who priced conduit at 15% and service calls
    # at 60% meant those numbers.
    default_markup_bps: int = 0


@dataclass(slots=True, frozen=True)
class MatchedTask:
    """An extracted task paired with its pricebook match, if any.

    An unmatched task is *not* dropped — it becomes a zero-cost line item the
    contractor prices by hand. Silently discarding scope the customer
    described is worse than surfacing it at $0.
    """

    task: ExtractedTask
    match: PricebookMatch | None = None

    @property
    def is_matched(self) -> bool:
        return self.match is not None


@dataclass(slots=True, frozen=True)
class LineItemDraft:
    """A line item ready to POST to quote-service.

    Deliberately carries `unit_cost_minor` + `markup_bps` and **not**
    `unit_price_minor`: quote-service computes the price from those two
    (`LineItemCreate.unit_price_minor` is documented as derived when omitted).
    Duplicating that arithmetic here would create a second source of truth for
    pricing that could silently drift.
    """

    description: str
    kind: str
    quantity: Decimal
    unit: str
    unit_cost_minor: int
    markup_bps: int
    pricebook_item_id: UUID | None = None
    sort_order: int = 0


@dataclass(slots=True, frozen=True)
class AiUsage:
    """One metered AI call, for billing and cost control."""

    feature: AiFeature
    model_id: str
    input_kind: str
    tokens_used: int
    cost_minor: int
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AiUsageRecord(AiUsage):
    """A persisted `AiUsage`, as read back for the /usage endpoint."""

    id: UUID | None = None
    created_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class QuoteAssistantResult:
    """Everything a voice/text-to-quote run produced."""

    quote_id: UUID
    scope: ExtractedScope
    matched_tasks: tuple[MatchedTask, ...]
    model_id: str
    tokens_used: int
    input_kind: InputKind
    transcript: TranscriptionResult | None = None

    @property
    def unmatched_count(self) -> int:
        return sum(1 for item in self.matched_tasks if not item.is_matched)
