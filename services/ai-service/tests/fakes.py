"""In-memory fakes for every port.

The whole point of the Protocol ports: no test needs an API key, a network,
or a database (conventions §3).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.models import (
    AiFeature,
    AiUsage,
    AiUsageRecord,
    DetectedEquipment,
    DocumentKind,
    EquipmentCondition,
    EquipmentDetectionResult,
    ExtractedScope,
    ExtractedTask,
    LineItemDraft,
    MatchedTask,
    MissingItem,
    MissingItemsResult,
    OcrDocumentResult,
    OcrLineItem,
    PricebookMatch,
    PricingAnalysisResult,
    PricingSuggestion,
    QuoteLineItem,
    QuoteSnapshot,
    SalesCoachResult,
    SalesSuggestion,
    SalesSuggestionKind,
    TaskCategory,
    Trade,
    TranscriptionResult,
)


def make_task(
    item_name: str = "200A main breaker panel",
    *,
    category: TaskCategory = TaskCategory.MATERIAL,
    quantity: str = "1",
    unit: str = "each",
    description: str | None = None,
) -> ExtractedTask:
    return ExtractedTask(
        description=description or item_name,
        category=category,
        item_name=item_name,
        quantity=Decimal(quantity),
        unit=unit,
    )


def make_scope(tasks: tuple[ExtractedTask, ...] | None = None) -> ExtractedScope:
    return ExtractedScope(
        trade=Trade.ELECTRICAL,
        summary="Panel upgrade and LED lighting",
        tasks=tasks
        if tasks is not None
        else (
            make_task("200A main breaker panel"),
            make_task(
                "Panel installation",
                category=TaskCategory.LABOR,
                quantity="4",
                unit="hr",
            ),
        ),
        notes="Permit required for panel upgrade.",
    )


def make_match(
    *, unit_cost_minor: int = 85_000, markup_bps: int = 0, unit: str = "each", kind: str = "material"
) -> PricebookMatch:
    return PricebookMatch(
        pricebook_item_id=uuid4(),
        name="200A main breaker panel",
        kind=kind,
        unit_cost_minor=unit_cost_minor,
        unit=unit,
        confidence=0.95,
        default_markup_bps=markup_bps,
    )


def make_line_item(
    *,
    description: str = "200A main breaker panel",
    kind: str = "material",
    quantity: str = "1",
    unit: str = "each",
    unit_cost_minor: int = 80_000,
    markup_bps: int = 3000,
    unit_price_minor: int = 104_000,
    line_total_minor: int | None = None,
    pricebook_item_id: UUID | None = None,
) -> QuoteLineItem:
    qty = Decimal(quantity)
    return QuoteLineItem(
        id=uuid4(),
        kind=kind,
        description=description,
        quantity=qty,
        unit=unit,
        unit_cost_minor=unit_cost_minor,
        markup_bps=markup_bps,
        unit_price_minor=unit_price_minor,
        line_total_minor=(
            line_total_minor if line_total_minor is not None else int(unit_price_minor * qty)
        ),
        pricebook_item_id=pricebook_item_id,
    )


def make_snapshot(
    line_items: tuple[QuoteLineItem, ...] | None = None,
    *,
    trade_hint: str | None = "electrical",
    quote_id: UUID | None = None,
) -> QuoteSnapshot:
    items = (
        line_items
        if line_items is not None
        else (
            make_line_item(),
            make_line_item(
                description="Panel installation labor",
                kind="labor",
                quantity="4",
                unit="hr",
                unit_cost_minor=6_000,
                markup_bps=5000,
                unit_price_minor=9_000,
            ),
        )
    )
    subtotal = sum(item.line_total_minor for item in items)
    return QuoteSnapshot(
        quote_id=quote_id or uuid4(),
        trade_hint=trade_hint,
        currency="USD",
        tax_rate_bps=875,
        subtotal_minor=subtotal,
        tax_minor=round(subtotal * 875 / 10_000),
        total_minor=subtotal + round(subtotal * 875 / 10_000),
        line_items=items,
    )


class FakeTranscriptionService:
    def __init__(self, text: str = "Replace the panel with a 200 amp", duration: float = 12.0):
        self.text = text
        self.duration = duration
        self.calls: list[tuple[int, str]] = []

    def transcribe(self, audio_bytes: bytes, mime_type: str) -> TranscriptionResult:
        self.calls.append((len(audio_bytes), mime_type))
        return TranscriptionResult(
            text=self.text, language="en", duration_seconds=self.duration, model_id="whisper-1"
        )


class FakeScopeExtractor:
    def __init__(self, scope: ExtractedScope | None = None, *, tokens: int = 1_200):
        self.scope = scope if scope is not None else make_scope()
        self.tokens = tokens
        self.calls: list[tuple[str, str | None]] = []

    def extract_scope(
        self, text: str, trade_hint: str | None = None
    ) -> tuple[ExtractedScope, AiUsage]:
        self.calls.append((text, trade_hint))
        usage = AiUsage(
            feature=AiFeature.VOICE,
            model_id="claude-opus-5",
            input_kind="text",
            tokens_used=self.tokens,
            cost_minor=7,
        )
        return self.scope, usage


class FakeScopeNarrator:
    def __init__(self, text: str = "We will replace the existing panel..."):
        self.text = text
        self.calls: list[tuple[ExtractedScope, str]] = []

    def write_scope(self, scope: ExtractedScope, tone: str) -> tuple[str, AiUsage]:
        self.calls.append((scope, tone))
        usage = AiUsage(
            feature=AiFeature.SCOPE_WRITER,
            model_id="claude-opus-5",
            input_kind="text",
            tokens_used=400,
            cost_minor=2,
        )
        return self.text, usage


def make_equipment(
    name: str = "200A main breaker panel",
    *,
    category: TaskCategory = TaskCategory.MATERIAL,
    condition: EquipmentCondition = EquipmentCondition.GOOD,
    quantity: str = "1",
    unit: str = "each",
) -> DetectedEquipment:
    return DetectedEquipment(
        name=name,
        category=category,
        condition=condition,
        quantity=Decimal(quantity),
        unit=unit,
    )


def make_detection(
    equipment: tuple[DetectedEquipment, ...] | None = None,
) -> EquipmentDetectionResult:
    return EquipmentDetectionResult(
        trade=Trade.ELECTRICAL,
        summary="200A panel upgrade",
        equipment=equipment if equipment is not None else (make_equipment(),),
        notes="Panel shows signs of wear at the main lugs.",
    )


class FakeVisionDetector:
    def __init__(
        self, detection: EquipmentDetectionResult | None = None, *, tokens: int = 1_500
    ):
        self.detection = detection if detection is not None else make_detection()
        self.tokens = tokens
        self.calls: list[tuple[int, str, str | None]] = []

    def detect_equipment(
        self, image_bytes: bytes, mime_type: str, trade_hint: str | None = None
    ) -> tuple[EquipmentDetectionResult, AiUsage]:
        self.calls.append((len(image_bytes), mime_type, trade_hint))
        usage = AiUsage(
            feature=AiFeature.VISION,
            model_id="claude-opus-5",
            input_kind="vision",
            tokens_used=self.tokens,
            cost_minor=11,
        )
        return self.detection, usage


def make_ocr_line_item(
    item_name: str = "3/4in copper pipe",
    *,
    category: TaskCategory = TaskCategory.MATERIAL,
    quantity: str = "1",
    unit: str = "each",
    unit_cost_minor: int | None = 1_200,
) -> OcrLineItem:
    return OcrLineItem(
        description=item_name,
        category=category,
        item_name=item_name,
        quantity=Decimal(quantity),
        unit=unit,
        unit_cost_minor=unit_cost_minor,
    )


def make_document_result(
    line_items: tuple[OcrLineItem, ...] | None = None,
    *,
    document_kind: DocumentKind = DocumentKind.INVOICE,
) -> OcrDocumentResult:
    return OcrDocumentResult(
        document_kind=document_kind,
        trade=Trade.PLUMBING,
        summary="Copper pipe and fittings restock",
        line_items=line_items if line_items is not None else (make_ocr_line_item(),),
        vendor_name="Acme Supply Co.",
        document_date="2026-07-15",
        reference_number="INV-4471",
        notes="",
    )


class FakeDocumentExtractor:
    def __init__(
        self, extraction: OcrDocumentResult | None = None, *, tokens: int = 1_600
    ):
        self.extraction = extraction if extraction is not None else make_document_result()
        self.tokens = tokens
        self.calls: list[tuple[int, str, str | None]] = []

    def extract_document(
        self, document_bytes: bytes, mime_type: str, document_kind_hint: str | None = None
    ) -> tuple[OcrDocumentResult, AiUsage]:
        self.calls.append((len(document_bytes), mime_type, document_kind_hint))
        usage = AiUsage(
            feature=AiFeature.OCR,
            model_id="claude-opus-5",
            input_kind="ocr",
            tokens_used=self.tokens,
            cost_minor=12,
        )
        return self.extraction, usage


class FakePricebookMatcher:
    """Matches by exact `item_name` against a supplied table."""

    def __init__(self, matches: dict[str, PricebookMatch] | None = None):
        self.matches = matches or {}
        self.calls: list[list[ExtractedTask]] = []

    def match(
        self, tenant_id: UUID, user_id: UUID | None, tasks: list[ExtractedTask]
    ) -> list[MatchedTask]:
        self.calls.append(list(tasks))
        return [MatchedTask(task=task, match=self.matches.get(task.item_name)) for task in tasks]


class FakeQuoteCreator:
    def __init__(self, quote_id: UUID | None = None):
        self.quote_id = quote_id or uuid4()
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "customer_id": customer_id,
                "title": title,
                "created_via": created_via,
                "tax_rate_bps": tax_rate_bps,
                "line_items": line_items,
            }
        )
        return self.quote_id


class InMemoryUsageRepository:
    def __init__(self, spend_today: int = 0):
        self.spend_today = spend_today
        self.recorded: list[AiUsage] = []

    def record(self, tenant_id: UUID, usage: AiUsage) -> None:
        self.recorded.append(usage)

    def list_for_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AiUsageRecord]:
        return []

    def spend_today_minor(self, tenant_id: UUID) -> int:
        return self.spend_today


class FakeQuoteReader:
    """Returns a canned snapshot, or raises QuoteNotFoundError when told to."""

    def __init__(self, snapshot: QuoteSnapshot | None = None, *, found: bool = True):
        self.snapshot = snapshot if snapshot is not None else make_snapshot()
        self.found = found
        self.calls: list[UUID] = []

    def get_quote(
        self, tenant_id: UUID, user_id: UUID | None, quote_id: UUID
    ) -> QuoteSnapshot:
        from app.domain.errors import QuoteNotFoundError

        self.calls.append(quote_id)
        if not self.found:
            raise QuoteNotFoundError(str(quote_id))
        return self.snapshot


def _copilot_usage(tokens: int = 900, cost_minor: int = 3) -> AiUsage:
    return AiUsage(
        feature=AiFeature.COPILOT,
        model_id="claude-sonnet-5",
        input_kind="text",
        tokens_used=tokens,
        cost_minor=cost_minor,
    )


class FakeCopilotAnalyzer:
    """Canned analyzer. Margin numbers come from the real pure math module so
    route/use-case tests exercise realistic responses."""

    def __init__(
        self,
        *,
        recommendation: str = "Margins look healthy overall.",
        missing: tuple[MissingItem, ...] | None = None,
        completeness_score: int = 80,
    ):
        self.recommendation = recommendation
        self.missing = missing
        self.completeness_score = completeness_score
        self.pricing_calls: list[QuoteSnapshot] = []
        self.missing_calls: list[tuple[QuoteSnapshot, str | None]] = []

    def analyze_pricing(
        self, quote: QuoteSnapshot, pricebook_matches: Mapping[UUID, PricebookMatch]
    ) -> tuple[PricingAnalysisResult, AiUsage]:
        from app.application.margin import compute_margin

        self.pricing_calls.append(quote)
        suggestions = tuple(
            PricingSuggestion(
                line_item_id=item.id,
                current_unit_cost_minor=item.unit_cost_minor,
                current_markup_bps=item.markup_bps,
                current_unit_price_minor=item.unit_price_minor,
                suggested_unit_cost_minor=None,
                suggested_markup_bps=None,
                pricebook_unit_cost_minor=(
                    pricebook_matches[item.id].unit_cost_minor
                    if item.id in pricebook_matches
                    else None
                ),
                reasoning="looks fine",
            )
            for item in quote.line_items
        )
        result = PricingAnalysisResult(
            suggestions=suggestions,
            margin=compute_margin(quote, self.recommendation),
            model_id="claude-sonnet-5",
            tokens_used=900,
        )
        return result, _copilot_usage()

    def find_missing_items(
        self, quote: QuoteSnapshot, job_description: str | None = None
    ) -> tuple[MissingItemsResult, AiUsage]:
        self.missing_calls.append((quote, job_description))
        missing = (
            self.missing
            if self.missing is not None
            else (
                MissingItem(
                    description="Permit for panel upgrade",
                    category="labor",
                    item_name="electrical permit",
                    estimated_quantity=Decimal(1),
                    unit="each",
                    reasoning="A 200A service change requires a permit.",
                    priority="critical",
                ),
            )
        )
        result = MissingItemsResult(
            missing=missing,
            trade=Trade.ELECTRICAL,
            completeness_score=self.completeness_score,
            summary="Add a permit line and you're set.",
            model_id="claude-sonnet-5",
            tokens_used=700,
        )
        return result, _copilot_usage(tokens=700)


def make_sales_suggestion(
    item_name: str = "Whole-home surge protector",
    *,
    kind: SalesSuggestionKind = SalesSuggestionKind.CROSS_SELL,
    estimated_price_minor: int | None = 25_000,
) -> SalesSuggestion:
    return SalesSuggestion(
        kind=kind,
        item_name=item_name,
        description=f"{item_name} installed alongside the panel work.",
        reasoning="Panel upgrades are the natural moment to add this.",
        talking_point=f"While we're in the panel, want me to add a {item_name.lower()}?",
        estimated_price_minor=estimated_price_minor,
    )


class FakeSalesCoachAnalyzer:
    def __init__(
        self,
        suggestions: tuple[SalesSuggestion, ...] | None = None,
        *,
        summary: str = "One relevant cross-sell opportunity found.",
        tokens: int = 800,
    ):
        self.suggestions = suggestions if suggestions is not None else (make_sales_suggestion(),)
        self.summary = summary
        self.tokens = tokens
        self.calls: list[QuoteSnapshot] = []

    def suggest(self, quote: QuoteSnapshot) -> tuple[SalesCoachResult, AiUsage]:
        self.calls.append(quote)
        usage = AiUsage(
            feature=AiFeature.SALES_COACH,
            model_id="claude-sonnet-5",
            input_kind="text",
            tokens_used=self.tokens,
            cost_minor=4,
        )
        result = SalesCoachResult(
            suggestions=self.suggestions,
            summary=self.summary,
            model_id="claude-sonnet-5",
            tokens_used=self.tokens,
        )
        return result, usage


class FakeTextRewriter:
    def __init__(self, *, prefix: str = "Professionally: "):
        self.prefix = prefix
        self.calls: list[tuple[list[str], str, str | None]] = []

    def rewrite(
        self, texts: list[str], tone: str, context_hint: str | None = None
    ) -> tuple[list[str], AiUsage]:
        self.calls.append((list(texts), tone, context_hint))
        return [f"{self.prefix}{text}" for text in texts], _copilot_usage(tokens=300, cost_minor=1)


class FakeDependencies:
    """Stands in for the composition root in route tests."""

    def __init__(self) -> None:
        self.transcription_service = FakeTranscriptionService()
        self.scope_extractor = FakeScopeExtractor()
        self.scope_narrator = FakeScopeNarrator()
        self.pricebook_matcher = FakePricebookMatcher()
        self.quote_creator_impl = FakeQuoteCreator()
        self.quote_reader_impl = FakeQuoteReader()
        self.copilot_analyzer_impl = FakeCopilotAnalyzer()
        self.text_rewriter_impl = FakeTextRewriter()
        self.vision_detector_impl = FakeVisionDetector()
        self.document_extractor_impl = FakeDocumentExtractor()
        self.sales_coach_analyzer_impl = FakeSalesCoachAnalyzer()

    def transcription(self): return self.transcription_service
    def extractor(self): return self.scope_extractor
    def narrator(self): return self.scope_narrator
    def matcher(self): return self.pricebook_matcher
    def quote_creator(self): return self.quote_creator_impl
    def quote_reader(self): return self.quote_reader_impl
    def copilot_analyzer(self): return self.copilot_analyzer_impl
    def text_rewriter(self): return self.text_rewriter_impl
    def vision_detector(self): return self.vision_detector_impl
    def document_extractor(self): return self.document_extractor_impl
    def sales_coach_analyzer(self): return self.sales_coach_analyzer_impl
