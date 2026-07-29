"""Pydantic DTOs for the AI Quote Assistant HTTP surface."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.models import (
    ExtractedScope,
    ExtractedTask,
    QuoteAssistantResult,
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


class AiUsageResponse(BaseModel):
    id: UUID | None
    feature: str
    model_id: str
    input_kind: str
    tokens_used: int
    cost_minor: int
    created_at: datetime | None


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
