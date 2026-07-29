"""In-memory fakes for every port.

The whole point of the Protocol ports: no test needs an API key, a network,
or a database (conventions §3).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.models import (
    AiFeature,
    AiUsage,
    AiUsageRecord,
    ExtractedScope,
    ExtractedTask,
    LineItemDraft,
    MatchedTask,
    PricebookMatch,
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


class FakeDependencies:
    """Stands in for the composition root in route tests."""

    def __init__(self) -> None:
        self.transcription_service = FakeTranscriptionService()
        self.scope_extractor = FakeScopeExtractor()
        self.scope_narrator = FakeScopeNarrator()
        self.pricebook_matcher = FakePricebookMatcher()
        self.quote_creator_impl = FakeQuoteCreator()

    def transcription(self): return self.transcription_service
    def extractor(self): return self.scope_extractor
    def narrator(self): return self.scope_narrator
    def matcher(self): return self.pricebook_matcher
    def quote_creator(self): return self.quote_creator_impl
