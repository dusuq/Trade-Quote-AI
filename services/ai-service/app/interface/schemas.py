"""Pydantic DTOs for the AI Quote Assistant HTTP surface."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.models import (
    EquipmentCondition,
    EquipmentDetectionOutcome,
    ExtractedScope,
    ExtractedTask,
    MissingItemsResult,
    OcrExtractionOutcome,
    PricingAnalysisResult,
    QuoteAssistantResult,
    RewriteResult,
    TaskCategory,
    Trade,
)


class TextToQuoteRequest(BaseModel):
    text: str = Field(min_length=10, max_length=10_000)
    customer_id: UUID
    property_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    trade_hint: str | None = Field(default=None, max_length=64)
    tax_rate_bps: int = Field(default=0, ge=0, le=100_000)
    default_markup_bps: int = Field(default=3000, ge=0, le=100_000)


class ExtractedTaskResponse(BaseModel):
    description: str
    category: TaskCategory
    item_name: str
    quantity: Decimal
    unit: str
    pricebook_item_id: UUID | None = None
    match_confidence: float | None = None
    unit_cost_minor: int | None = None


class QuoteDraftResponse(BaseModel):
    quote_id: UUID
    trade: Trade
    summary: str
    notes: str
    tasks: list[ExtractedTaskResponse]
    unmatched_count: int
    model_id: str
    tokens_used: int
    input_kind: str
    transcript: str | None = None
    language: str | None = None


class ScopeTaskInput(BaseModel):
    description: str = Field(min_length=1)
    category: TaskCategory = TaskCategory.MATERIAL
    item_name: str = Field(min_length=1)
    quantity: Decimal = Field(default=Decimal(1), gt=0)
    unit: str = "each"


class ScopeWriterRequest(BaseModel):
    trade: Trade
    summary: str = Field(min_length=1, max_length=1_000)
    tasks: list[ScopeTaskInput] = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2_000)
    tone: str = "professional"

    def to_scope(self) -> ExtractedScope:
        return ExtractedScope(
            trade=self.trade,
            summary=self.summary,
            tasks=tuple(
                ExtractedTask(
                    description=task.description,
                    category=task.category,
                    item_name=task.item_name,
                    quantity=task.quantity,
                    unit=task.unit,
                )
                for task in self.tasks
            ),
            notes=self.notes,
        )


class ScopeWriterResponse(BaseModel):
    scope_text: str
    model_id: str
    tokens_used: int


# ── AI Vision (M18 / T304) ───────────────────────────────────────────────────


class DetectedEquipmentResponse(BaseModel):
    name: str
    category: TaskCategory
    condition: EquipmentCondition
    quantity: Decimal
    unit: str
    pricebook_item_id: UUID | None = None
    match_confidence: float | None = None
    unit_cost_minor: int | None = None


class EquipmentDetectionResponse(BaseModel):
    trade: Trade
    summary: str
    notes: str
    equipment: list[DetectedEquipmentResponse]
    unmatched_count: int
    model_id: str
    tokens_used: int


def to_equipment_detection_response(
    outcome: EquipmentDetectionOutcome,
) -> EquipmentDetectionResponse:
    """Flatten a detection outcome into the wire shape.

    `matched_tasks` is 1:1 with `outcome.detection.equipment`, in order —
    `detect_and_match` builds both from the same task list — so zipping them
    is safe.
    """
    return EquipmentDetectionResponse(
        trade=outcome.detection.trade,
        summary=outcome.detection.summary,
        notes=outcome.detection.notes,
        equipment=[
            DetectedEquipmentResponse(
                name=item.name,
                category=item.category,
                condition=item.condition,
                quantity=item.quantity,
                unit=item.unit,
                pricebook_item_id=matched.match.pricebook_item_id if matched.match else None,
                match_confidence=round(matched.match.confidence, 3) if matched.match else None,
                unit_cost_minor=matched.match.unit_cost_minor if matched.match else None,
            )
            for item, matched in zip(
                outcome.detection.equipment, outcome.matched_tasks, strict=True
            )
        ],
        unmatched_count=outcome.unmatched_count,
        model_id=outcome.model_id,
        tokens_used=outcome.tokens_used,
    )


# ── AI OCR (M19 / T305) ──────────────────────────────────────────────────────


class OcrLineItemResponse(BaseModel):
    description: str
    category: TaskCategory
    item_name: str
    quantity: Decimal
    unit: str
    extracted_unit_cost_minor: int | None = None
    pricebook_item_id: UUID | None = None
    match_confidence: float | None = None
    unit_cost_minor: int | None = None


class DocumentExtractionResponse(BaseModel):
    document_kind: str
    trade: Trade
    summary: str
    vendor_name: str
    document_date: str
    reference_number: str
    notes: str
    line_items: list[OcrLineItemResponse]
    unmatched_count: int
    model_id: str
    tokens_used: int


def to_document_extraction_response(
    outcome: OcrExtractionOutcome,
) -> DocumentExtractionResponse:
    """Flatten an OCR extraction outcome into the wire shape.

    `matched_tasks` is 1:1 with `outcome.extraction.line_items`, in order —
    `extract_and_match` builds both from the same task list — so zipping them
    is safe (same pattern as `to_equipment_detection_response`).
    """
    extraction = outcome.extraction
    return DocumentExtractionResponse(
        document_kind=extraction.document_kind.value,
        trade=extraction.trade,
        summary=extraction.summary,
        vendor_name=extraction.vendor_name,
        document_date=extraction.document_date,
        reference_number=extraction.reference_number,
        notes=extraction.notes,
        line_items=[
            OcrLineItemResponse(
                description=item.description,
                category=item.category,
                item_name=item.item_name,
                quantity=item.quantity,
                unit=item.unit,
                extracted_unit_cost_minor=item.unit_cost_minor,
                pricebook_item_id=matched.match.pricebook_item_id if matched.match else None,
                match_confidence=round(matched.match.confidence, 3) if matched.match else None,
                unit_cost_minor=matched.match.unit_cost_minor if matched.match else None,
            )
            for item, matched in zip(
                extraction.line_items, outcome.matched_tasks, strict=True
            )
        ],
        unmatched_count=outcome.unmatched_count,
        model_id=outcome.model_id,
        tokens_used=outcome.tokens_used,
    )


class AiUsageResponse(BaseModel):
    id: UUID | None
    feature: str
    model_id: str
    input_kind: str
    tokens_used: int
    cost_minor: int
    created_at: datetime | None


# ── Copilot (T202) requests ───────────────────────────────────────────────────


class AnalyzePricingRequest(BaseModel):
    quote_id: UUID


class MissingItemsRequest(BaseModel):
    quote_id: UUID
    job_description: str | None = Field(
        default=None,
        max_length=10_000,
        description="Optional original job description for better context",
    )


class RewriteRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=50)
    tone: str = "professional"
    context_hint: str | None = Field(
        default=None,
        max_length=500,
        description="E.g. 'electrical panel upgrade' — helps the model understand trade context",
    )


# ── Copilot responses ─────────────────────────────────────────────────────────


class PricingSuggestionResponse(BaseModel):
    line_item_id: UUID
    current_unit_cost_minor: int
    current_markup_bps: int
    current_unit_price_minor: int
    suggested_markup_bps: int | None
    pricebook_unit_cost_minor: int | None
    reasoning: str


class MarginAnalysisResponse(BaseModel):
    total_cost_minor: int
    total_revenue_minor: int
    gross_margin_bps: int
    average_markup_bps: int
    low_margin_item_ids: list[UUID]
    recommendation: str


class PricingAnalysisResponse(BaseModel):
    quote_id: UUID
    suggestions: list[PricingSuggestionResponse]
    margin: MarginAnalysisResponse
    model_id: str
    tokens_used: int


class MissingItemResponse(BaseModel):
    description: str
    category: str
    item_name: str
    estimated_quantity: Decimal
    unit: str
    reasoning: str
    priority: str


class MissingItemsResponse(BaseModel):
    quote_id: UUID
    trade: str
    completeness_score: int
    summary: str
    missing: list[MissingItemResponse]
    model_id: str
    tokens_used: int


class RewriteResponse(BaseModel):
    rewritten: list[str]
    model_id: str
    tokens_used: int


def to_pricing_analysis_response(
    quote_id: UUID, result: PricingAnalysisResult
) -> PricingAnalysisResponse:
    return PricingAnalysisResponse(
        quote_id=quote_id,
        suggestions=[
            PricingSuggestionResponse(
                line_item_id=s.line_item_id,
                current_unit_cost_minor=s.current_unit_cost_minor,
                current_markup_bps=s.current_markup_bps,
                current_unit_price_minor=s.current_unit_price_minor,
                suggested_markup_bps=s.suggested_markup_bps,
                pricebook_unit_cost_minor=s.pricebook_unit_cost_minor,
                reasoning=s.reasoning,
            )
            for s in result.suggestions
        ],
        margin=MarginAnalysisResponse(
            total_cost_minor=result.margin.total_cost_minor,
            total_revenue_minor=result.margin.total_revenue_minor,
            gross_margin_bps=result.margin.gross_margin_bps,
            average_markup_bps=result.margin.average_markup_bps,
            low_margin_item_ids=list(result.margin.low_margin_item_ids),
            recommendation=result.margin.recommendation,
        ),
        model_id=result.model_id,
        tokens_used=result.tokens_used,
    )


def to_missing_items_response(
    quote_id: UUID, result: MissingItemsResult
) -> MissingItemsResponse:
    return MissingItemsResponse(
        quote_id=quote_id,
        trade=result.trade.value,
        completeness_score=result.completeness_score,
        summary=result.summary,
        missing=[
            MissingItemResponse(
                description=item.description,
                category=item.category,
                item_name=item.item_name,
                estimated_quantity=item.estimated_quantity,
                unit=item.unit,
                reasoning=item.reasoning,
                priority=item.priority,
            )
            for item in result.missing
        ],
        model_id=result.model_id,
        tokens_used=result.tokens_used,
    )


def to_rewrite_response(result: RewriteResult) -> RewriteResponse:
    return RewriteResponse(
        rewritten=list(result.rewritten),
        model_id=result.model_id,
        tokens_used=result.tokens_used,
    )


def to_quote_draft_response(result: QuoteAssistantResult) -> QuoteDraftResponse:
    """Flatten a pipeline result into the wire shape."""
    return QuoteDraftResponse(
        quote_id=result.quote_id,
        trade=result.scope.trade,
        summary=result.scope.summary,
        notes=result.scope.notes,
        tasks=[
            ExtractedTaskResponse(
                description=item.task.description,
                category=item.task.category,
                item_name=item.task.item_name,
                quantity=item.task.quantity,
                unit=item.task.unit,
                pricebook_item_id=item.match.pricebook_item_id if item.match else None,
                match_confidence=round(item.match.confidence, 3) if item.match else None,
                unit_cost_minor=item.match.unit_cost_minor if item.match else None,
            )
            for item in result.matched_tasks
        ],
        unmatched_count=result.unmatched_count,
        model_id=result.model_id,
        tokens_used=result.tokens_used,
        input_kind=result.input_kind.value,
        transcript=result.transcript.text if result.transcript else None,
        language=result.transcript.language if result.transcript else None,
    )
