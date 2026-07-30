"""Composition root.

Adapters are built here, behind a single swappable object, so route tests can
replace every external dependency (Claude, Whisper, pricebook, quote-service)
with a fake by assigning one attribute — and so no test needs an API key or a
network.
"""

from __future__ import annotations

from app.config import settings
from app.domain.protocols import (
    CopilotAnalyzer,
    PricebookMatcher,
    QuoteCreator,
    QuoteReader,
    ScopeExtractor,
    ScopeNarrator,
    TextRewriter,
    TranscriptionService,
)
from app.infrastructure.claude_adapter import ClaudeScopeExtractor, ClaudeScopeNarrator
from app.infrastructure.copilot_claude_adapter import (
    ClaudeCopilotAnalyzer,
    ClaudeTextRewriter,
)
from app.infrastructure.http import ServiceClient
from app.infrastructure.pricebook_client import HttpPricebookMatcher
from app.infrastructure.quote_client import HttpQuoteCreator
from app.infrastructure.quote_reader import HttpQuoteReader
from app.infrastructure.whisper_adapter import WhisperTranscriptionService


class Dependencies:
    """Lazily-built singletons. One `httpx.Client` per upstream, reused."""

    def __init__(self) -> None:
        self._pricebook_service: ServiceClient | None = None
        self._quote_service: ServiceClient | None = None

    def _service(self, name: str, base_url: str) -> ServiceClient:
        return ServiceClient(
            service_name=name,
            base_url=base_url,
            timeout_seconds=settings.upstream_timeout_seconds,
            max_attempts=settings.upstream_max_attempts,
        )

    def transcription(self) -> TranscriptionService:
        return WhisperTranscriptionService(settings.openai_api_key, settings.whisper_model)

    def extractor(self) -> ScopeExtractor:
        return ClaudeScopeExtractor(settings.anthropic_api_key, settings.claude_model)

    def narrator(self) -> ScopeNarrator:
        return ClaudeScopeNarrator(settings.anthropic_api_key, settings.claude_model)

    def matcher(self) -> PricebookMatcher:
        if self._pricebook_service is None:
            self._pricebook_service = self._service(
                "pricebook-service", settings.pricebook_service_url
            )
        return HttpPricebookMatcher(self._pricebook_service)

    def quote_creator(self) -> QuoteCreator:
        if self._quote_service is None:
            self._quote_service = self._service("quote-service", settings.quote_service_url)
        return HttpQuoteCreator(self._quote_service)

    def quote_reader(self) -> QuoteReader:
        # Shares the one quote-service client with quote_creator — a read and a
        # write against the same upstream, one pooled httpx client.
        if self._quote_service is None:
            self._quote_service = self._service("quote-service", settings.quote_service_url)
        return HttpQuoteReader(self._quote_service)

    def copilot_analyzer(self) -> CopilotAnalyzer:
        return ClaudeCopilotAnalyzer(settings.anthropic_api_key, settings.copilot_model)

    def text_rewriter(self) -> TextRewriter:
        return ClaudeTextRewriter(settings.anthropic_api_key, settings.copilot_model)


deps = Dependencies()
