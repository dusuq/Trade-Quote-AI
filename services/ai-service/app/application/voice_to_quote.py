"""Use case: audio -> transcript -> the text-to-quote pipeline."""

from __future__ import annotations

import dataclasses
from uuid import UUID

from app.application.audio import validate_audio
from app.application.line_items import DEFAULT_MARKUP_BPS
from app.application.text_to_quote import TextToQuoteUseCase
from app.domain.errors import TranscriptionError
from app.domain.events import DomainEvent
from app.domain.models import InputKind, QuoteAssistantResult
from app.domain.protocols import TranscriptionService


class VoiceToQuoteUseCase:
    """Transcription in front of the text pipeline.

    Composed rather than duplicated: once audio becomes text the two flows are
    identical, and forking them would let the voice path drift out of sync
    with the text path's pricing and matching behavior.
    """

    def __init__(
        self,
        transcription: TranscriptionService,
        text_to_quote: TextToQuoteUseCase,
        *,
        max_audio_bytes: int,
    ) -> None:
        self._transcription = transcription
        self._text_to_quote = text_to_quote
        self._max_audio_bytes = max_audio_bytes

    def execute(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        audio_bytes: bytes,
        mime_type: str,
        customer_id: UUID,
        property_id: UUID | None = None,
        title: str | None = None,
        trade_hint: str | None = None,
        tax_rate_bps: int = 0,
        default_markup_bps: int = DEFAULT_MARKUP_BPS,
    ) -> tuple[QuoteAssistantResult, list[DomainEvent]]:
        normalized_mime = validate_audio(
            size_bytes=len(audio_bytes),
            mime_type=mime_type,
            max_bytes=self._max_audio_bytes,
        )

        transcript = self._transcription.transcribe(audio_bytes, normalized_mime)
        if not transcript.text.strip():
            # Silence, or audio the model couldn't make anything of. Failing
            # here is much clearer than handing an empty string to the LLM and
            # getting a confidently invented scope back.
            raise TranscriptionError(
                "no speech was detected in the recording — please try again"
            )

        result, events = self._text_to_quote.execute(
            tenant_id=tenant_id,
            user_id=user_id,
            text=transcript.text,
            customer_id=customer_id,
            property_id=property_id,
            title=title,
            trade_hint=trade_hint,
            tax_rate_bps=tax_rate_bps,
            default_markup_bps=default_markup_bps,
            input_kind=InputKind.VOICE,
        )
        return dataclasses.replace(result, transcript=transcript), events
