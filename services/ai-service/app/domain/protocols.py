"""Ports. The application layer depends only on these, never on an SDK or
`httpx`, so every use case runs against in-memory fakes with no network and no
API keys (conventions §3).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from app.domain.models import (
    AiUsage,
    AiUsageRecord,
    EquipmentDetectionResult,
    ExtractedScope,
    ExtractedTask,
    LineItemDraft,
    MatchedTask,
    MissingItemsResult,
    OcrDocumentResult,
    PricebookMatch,
    PricingAnalysisResult,
    QuoteSnapshot,
    SalesCoachResult,
    TranscriptionResult,
)


class TranscriptionService(Protocol):
    def transcribe(self, audio_bytes: bytes, mime_type: str) -> TranscriptionResult: ...


class VisionDetector(Protocol):
    def detect_equipment(
        self, image_bytes: bytes, mime_type: str, trade_hint: str | None = None
    ) -> tuple[EquipmentDetectionResult, AiUsage]:
        """Identify trade equipment (panels, HVAC units, pipe, roofing, etc.)
        in a photo, plus the usage it cost."""
        ...


class DocumentExtractor(Protocol):
    def extract_document(
        self, document_bytes: bytes, mime_type: str, document_kind_hint: str | None = None
    ) -> tuple[OcrDocumentResult, AiUsage]:
        """Extract structured data (vendor, line items, totals) from a
        photographed supplier invoice, blueprint, or handwritten note, plus
        the usage it cost."""
        ...


class ScopeExtractor(Protocol):
    def extract_scope(
        self, text: str, trade_hint: str | None = None
    ) -> tuple[ExtractedScope, AiUsage]:
        """Turn free text into a structured scope, plus the usage it cost."""
        ...


class ScopeNarrator(Protocol):
    def write_scope(self, scope: ExtractedScope, tone: str) -> tuple[str, AiUsage]:
        """Turn a structured scope into customer-facing prose."""
        ...


class PricebookMatcher(Protocol):
    def match(
        self, tenant_id: UUID, user_id: UUID | None, tasks: list[ExtractedTask]
    ) -> list[MatchedTask]:
        """Pair each task with its best pricebook item, or None.

        Must return one entry per input task, in order — an unmatched task is
        carried through with `match=None`, never dropped.
        """
        ...


class QuoteCreator(Protocol):
    def create_quote(
        self,
        tenant_id: UUID,
        user_id: UUID | None,
        *,
        customer_id: UUID,
        property_id: UUID | None,
        title: str,
        created_via: str,
        tax_rate_bps: int,
        line_items: list[LineItemDraft],
    ) -> UUID:
        """Create the draft quote and return its id."""
        ...


class QuoteReader(Protocol):
    def get_quote(
        self, tenant_id: UUID, user_id: UUID | None, quote_id: UUID
    ) -> QuoteSnapshot:
        """Read the full quote with line items from quote-service.

        A `GET` per ADR-0003 — idempotent, safe to retry. Raises
        `QuoteNotFoundError` when the quote doesn't exist for this tenant.
        """
        ...


class CopilotAnalyzer(Protocol):
    def analyze_pricing(
        self,
        quote: QuoteSnapshot,
        pricebook_matches: Mapping[UUID, PricebookMatch],
    ) -> tuple[PricingAnalysisResult, AiUsage]:
        """Analyze pricing and margins, returning per-line suggestions.

        `pricebook_matches` is keyed by line-item id (only the lines that
        matched a catalog item appear). Margin numbers are computed by pure
        arithmetic, not the LLM — see `application/margin.py`.
        """
        ...

    def find_missing_items(
        self, quote: QuoteSnapshot, job_description: str | None = None
    ) -> tuple[MissingItemsResult, AiUsage]:
        """Detect missing materials/labor/equipment for this trade."""
        ...


class SalesCoachAnalyzer(Protocol):
    def suggest(self, quote: QuoteSnapshot) -> tuple[SalesCoachResult, AiUsage]:
        """Suggest upsells, warranty/maintenance add-ons, and cross-sell items
        for this quote, plus the usage it cost. Advisory only — never adds
        anything to the quote itself."""
        ...


class TextRewriter(Protocol):
    def rewrite(
        self, texts: list[str], tone: str, context_hint: str | None = None
    ) -> tuple[list[str], AiUsage]:
        """Rewrite descriptions/scope text in the given tone.

        Returns exactly one rewritten string per input, in order.
        """
        ...


class AiUsageRepository(Protocol):
    def record(self, tenant_id: UUID, usage: AiUsage) -> None: ...
    def list_for_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AiUsageRecord]: ...
    def spend_today_minor(self, tenant_id: UUID) -> int:
        """Total cost booked for this tenant today, for the daily cap."""
        ...
