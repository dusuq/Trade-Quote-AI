"""Domain errors. The interface layer maps these to HTTP status codes."""

from __future__ import annotations


class TranscriptionError(Exception):
    """Speech-to-text failed, or produced nothing usable."""


class ScopeExtractionError(Exception):
    """The LLM returned something that isn't a usable scope."""


class AudioTooLargeError(Exception):
    """Audio exceeds the configured size cap (→ 413)."""


class UnsupportedAudioFormatError(Exception):
    """Audio MIME type isn't one the transcriber accepts (→ 400)."""


class DailySpendCapExceededError(Exception):
    """The tenant has already spent its configured daily AI budget (→ 429).

    Checked before the model call, not after — the point is to not spend the
    money, so discovering it afterwards would defeat the control.
    """


class QuoteNotFoundError(Exception):
    """The requested quote doesn't exist, or belongs to another tenant (→ 404).

    quote-service enforces tenant scoping, so a cross-tenant id comes back as a
    404 there and surfaces here the same as a genuinely missing quote — which
    is the correct, non-leaking behaviour.
    """


class CopilotAnalysisError(Exception):
    """The LLM returned something that isn't a usable copilot analysis (→ 422).

    E.g. a rewrite that returned a different number of texts than it was given,
    or malformed structured output.
    """


class UpstreamServiceError(Exception):
    """A downstream service (pricebook, quote) failed or was unreachable.

    Raised by the shared HTTP client so no `httpx` exception ever escapes the
    infrastructure layer (ADR-0003 rule 4).
    """

    def __init__(self, service: str, detail: str, *, status_code: int | None = None) -> None:
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.detail = detail
        self.status_code = status_code
