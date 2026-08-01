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
    VISION = "vision"
    OCR = "ocr"


class AiFeature(str, enum.Enum):
    """Mirrors `AiUsageRecordedPayload.feature` in packages/types."""

    VOICE = "voice"
    SCOPE_WRITER = "scope_writer"
    COPILOT = "copilot"  # T202 — pricing/margin/missing-items/rewrite advice
    VISION = "vision"  # T304/M18 — photo-to-equipment-detection
    OCR = "ocr"  # T305/M19 — document-to-structured-data
    SALES_COACH = "sales_coach"  # T306/M17 — upsell/warranty/cross-sell suggestions


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


# ── AI Vision (M18 / T304) ──────────────────────────────────────────────────
#
# Photo -> equipment detection -> material list. `DetectedEquipment` is the
# vision-specific unit (adds `condition`, which text/voice have no analogue
# for); `application/vision.py` converts it down to `ExtractedTask` so the
# existing pricebook-matching and line-item pipeline is reused rather than
# forked for a third input modality.


class EquipmentCondition(str, enum.Enum):
    """Visual condition assessment. Advisory — never changes pricing on its
    own, but `worn`/`damaged` are surfaced so the contractor can flag a
    replacement instead of a repair."""

    NEW = "new"
    GOOD = "good"
    WORN = "worn"
    DAMAGED = "damaged"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class DetectedEquipment:
    """One piece of equipment identified in a photo."""

    name: str
    category: TaskCategory
    condition: EquipmentCondition
    quantity: Decimal
    unit: str
    notes: str = ""


@dataclass(slots=True, frozen=True)
class EquipmentDetectionResult:
    """Structured vision analysis of one photo."""

    trade: Trade
    summary: str
    equipment: tuple[DetectedEquipment, ...]
    notes: str = ""


@dataclass(slots=True, frozen=True)
class EquipmentDetectionOutcome:
    """Detection + pricebook matching, before any quote decision is made.

    Shared by both the detect-only ("material list") flow and the
    photo-to-quote flow — see `application/vision.py`.
    """

    detection: EquipmentDetectionResult
    matched_tasks: tuple[MatchedTask, ...]
    model_id: str
    tokens_used: int

    @property
    def unmatched_count(self) -> int:
        return sum(1 for item in self.matched_tasks if not item.is_matched)


# ── AI OCR (M19 / T305) ──────────────────────────────────────────────────────
#
# Document (supplier invoice / blueprint / handwritten job note) -> structured
# data. `OcrLineItem` is the OCR-specific unit — it adds `unit_cost_minor`
# (present when the source document itself states a price, e.g. an invoice
# line; `None` for a blueprint takeoff or a handwritten list, which don't).
# `application/ocr.py` converts it down to `ExtractedTask` so the existing
# pricebook-matching and line-item pipeline is reused rather than forked for a
# fourth input modality — same reasoning as M18's `equipment_to_extracted_scope`.
#
# `unit_cost_minor` is carried through to the extraction response for the
# contractor to compare against the pricebook, but deliberately never feeds
# `build_line_items` directly: quote-service remains the single source of
# truth for pricing (see `application/line_items.py`'s docstring), so an
# unmatched OCR line becomes a $0 line like any other unmatched task rather
# than opening a second, OCR-specific cost-injection path that could drift
# from the pricebook-authoritative one.


class DocumentKind(str, enum.Enum):
    """What kind of document was photographed. A closed set, deliberately —
    the extraction prompt and schema branch on it, so an open-ended free-text
    classification would make neither reliable."""

    INVOICE = "invoice"
    BLUEPRINT = "blueprint"
    HANDWRITTEN = "handwritten"


@dataclass(slots=True, frozen=True)
class OcrLineItem:
    """One row extracted from a document — an invoice line, a blueprint
    takeoff item, or a task from a handwritten list."""

    description: str
    category: TaskCategory
    item_name: str
    quantity: Decimal
    unit: str
    unit_cost_minor: int | None = None


@dataclass(slots=True, frozen=True)
class OcrDocumentResult:
    """Structured extraction of one document."""

    document_kind: DocumentKind
    trade: Trade
    summary: str
    line_items: tuple[OcrLineItem, ...]
    vendor_name: str = ""
    document_date: str = ""
    reference_number: str = ""
    notes: str = ""


@dataclass(slots=True, frozen=True)
class OcrExtractionOutcome:
    """Extraction + pricebook matching, before any quote decision is made.

    Shared by both the extract-only ("review the document") flow and the
    document-to-quote flow — see `application/ocr.py`.
    """

    extraction: OcrDocumentResult
    matched_tasks: tuple[MatchedTask, ...]
    model_id: str
    tokens_used: int

    @property
    def unmatched_count(self) -> int:
        return sum(1 for item in self.matched_tasks if not item.is_matched)


# ── Copilot (T202) ──────────────────────────────────────────────────────────
#
# Unlike the assistant models above, these describe an *existing* quote read
# back from quote-service and the advisory output the copilot produces from it.
# The copilot never mutates the quote — every model here is read-in or advice-out.


@dataclass(slots=True, frozen=True)
class QuoteLineItem:
    """A line item as read back from quote-service — the copilot's raw input.

    `quantity` is `Decimal`, not `float`, for the same reason it is on
    `ExtractedTask`: it multiplies a money value when computing line cost, so a
    binary-float quantity would leak rounding error straight into the margin
    arithmetic. `HttpQuoteReader` converts the wire float via `str` at the
    boundary (see `application/line_items.normalize_quantity`).
    """

    id: UUID
    kind: str
    description: str
    quantity: Decimal
    unit: str
    unit_cost_minor: int
    markup_bps: int
    unit_price_minor: int
    line_total_minor: int
    pricebook_item_id: UUID | None = None
    is_optional: bool = False


@dataclass(slots=True, frozen=True)
class QuoteSnapshot:
    """Read-only view of a quote for copilot analysis."""

    quote_id: UUID
    trade_hint: str | None  # inferred from the title; advisory only
    currency: str
    tax_rate_bps: int
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    line_items: tuple[QuoteLineItem, ...]


@dataclass(slots=True, frozen=True)
class PricingSuggestion:
    """One pricing suggestion for a single line item.

    The `current_*` values are copied verbatim from the quote; the
    `pricebook_unit_cost_minor` is what the tenant's own catalog says (or
    `None` when the item isn't in the pricebook); the `suggested_*` values and
    `reasoning` come from the LLM. A `None` suggestion means "current is fine".
    """

    line_item_id: UUID
    current_unit_cost_minor: int
    current_markup_bps: int
    current_unit_price_minor: int
    suggested_unit_cost_minor: int | None
    suggested_markup_bps: int | None
    pricebook_unit_cost_minor: int | None
    reasoning: str


@dataclass(slots=True, frozen=True)
class MarginAnalysis:
    """Quote-level margin summary.

    Every number here is computed by pure arithmetic in
    `application/margin.py` from the quote's own data — never by the LLM. The
    LLM contributes only `recommendation` (advisory prose).
    """

    total_cost_minor: int
    total_revenue_minor: int  # subtotal (excludes tax)
    gross_margin_bps: int  # (revenue - cost) / revenue * 10000
    average_markup_bps: int  # (revenue - cost) / cost * 10000
    low_margin_item_ids: tuple[UUID, ...]  # lines below LOW_MARGIN_THRESHOLD_BPS
    recommendation: str


@dataclass(slots=True, frozen=True)
class PricingAnalysisResult:
    """Complete analyze-pricing output."""

    suggestions: tuple[PricingSuggestion, ...]
    margin: MarginAnalysis
    model_id: str
    tokens_used: int


@dataclass(slots=True, frozen=True)
class MissingItem:
    """One item the copilot thinks is missing from the quote.

    `estimated_quantity` is `Decimal` for the same money-safety reason as
    elsewhere — the contractor may drop it straight onto a priced line.
    """

    description: str
    category: str  # "material" | "labor" | "equipment"
    item_name: str  # pricebook-searchable name
    estimated_quantity: Decimal
    unit: str
    reasoning: str  # why this is needed
    priority: str  # "critical" | "recommended" | "optional"


@dataclass(slots=True, frozen=True)
class MissingItemsResult:
    """Complete missing-items output."""

    missing: tuple[MissingItem, ...]
    trade: Trade
    completeness_score: int  # 0-100 estimate of how complete the quote is
    summary: str
    model_id: str
    tokens_used: int


@dataclass(slots=True, frozen=True)
class RewriteResult:
    """Complete rewrite output. `rewritten` is 1:1 with the input texts."""

    rewritten: tuple[str, ...]
    model_id: str
    tokens_used: int


# ── AI Sales Coach (T306 / M17) ───────────────────────────────────────────────
#
# Read-only, like the rest of the copilot family: reads an existing quote and
# returns advice, never mutates it. Unlike missing-items (which finds scope
# gaps the job itself needs), sales-coach finds *additional* things worth
# offering the customer — an upsell on what's already being installed, a
# warranty/maintenance-plan add-on, or a cross-sell into a different trade.


class SalesSuggestionKind(str, enum.Enum):
    """A closed set so the UI can group/badge suggestions without parsing
    free text — same reasoning as `Trade` and `DocumentKind`."""

    UPSELL = "upsell"
    WARRANTY = "warranty"
    CROSS_SELL = "cross_sell"


@dataclass(slots=True, frozen=True)
class SalesSuggestion:
    """One thing the contractor could offer the customer beyond the current
    quote. `estimated_price_minor` is a rough, advisory price hint — never
    priced against the pricebook and never added to the quote by this
    feature; the contractor decides whether and how to add it."""

    kind: SalesSuggestionKind
    item_name: str
    description: str
    reasoning: str
    talking_point: str
    estimated_price_minor: int | None = None


@dataclass(slots=True, frozen=True)
class SalesCoachResult:
    """Complete sales-coach output for one quote."""

    suggestions: tuple[SalesSuggestion, ...]
    summary: str
    model_id: str
    tokens_used: int
