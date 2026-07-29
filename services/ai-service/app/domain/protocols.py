"""Ports. The application layer depends only on these, never on an SDK or
`httpx`, so every use case runs against in-memory fakes with no network and no
API keys (conventions §3).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.models import (
    AiUsage,
    AiUsageRecord,
    ExtractedScope,
    ExtractedTask,
    LineItemDraft,
    MatchedTask,
    TranscriptionResult,
)


class TranscriptionService(Protocol):
    def transcribe(self, audio_bytes: bytes, mime_type: str) -> TranscriptionResult: ...


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


class AiUsageRepository(Protocol):
    def record(self, tenant_id: UUID, usage: AiUsage) -> None: ...
    def list_for_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[AiUsageRecord]: ...
    def spend_today_minor(self, tenant_id: UUID) -> int:
        """Total cost booked for this tenant today, for the daily cap."""
        ...
