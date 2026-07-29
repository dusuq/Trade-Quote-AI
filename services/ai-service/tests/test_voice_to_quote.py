"""The voice pipeline: transcription in front of the text pipeline."""

from __future__ import annotations

import uuid

import pytest

from app.application.text_to_quote import TextToQuoteUseCase
from app.application.voice_to_quote import VoiceToQuoteUseCase
from app.domain.errors import (
    AudioTooLargeError,
    TranscriptionError,
    UnsupportedAudioFormatError,
)
from app.domain.models import InputKind
from tests.fakes import (
    FakePricebookMatcher,
    FakeQuoteCreator,
    FakeScopeExtractor,
    FakeTranscriptionService,
    InMemoryUsageRepository,
)

TENANT = uuid.uuid4()
CUSTOMER = uuid.uuid4()
MAX_BYTES = 1_000


def build(*, transcript: str = "Replace the panel", max_bytes: int = MAX_BYTES):
    transcription = FakeTranscriptionService(transcript)
    extractor = FakeScopeExtractor()
    creator = FakeQuoteCreator()
    text_use_case = TextToQuoteUseCase(
        extractor, FakePricebookMatcher(), creator, InMemoryUsageRepository()
    )
    use_case = VoiceToQuoteUseCase(transcription, text_use_case, max_audio_bytes=max_bytes)
    return use_case, transcription, extractor, creator


def run(use_case, *, audio: bytes = b"x" * 100, mime: str = "audio/webm"):
    return use_case.execute(
        tenant_id=TENANT,
        user_id=None,
        audio_bytes=audio,
        mime_type=mime,
        customer_id=CUSTOMER,
    )


def test_transcribes_then_runs_the_text_pipeline() -> None:
    use_case, transcription, extractor, creator = build(transcript="Replace the 200 amp panel")

    result, _events = run(use_case)

    assert transcription.calls == [(100, "audio/webm")]
    assert extractor.calls[0][0] == "Replace the 200 amp panel"
    assert result.quote_id == creator.quote_id


def test_voice_runs_are_labelled_as_voice() -> None:
    use_case, _t, _e, creator = build()

    result, events = run(use_case)

    assert result.input_kind is InputKind.VOICE
    assert creator.calls[0]["created_via"] == "voice"
    assert events[0].payload["inputKind"] == "voice"


def test_transcript_is_returned_with_the_result() -> None:
    use_case, _t, _e, _c = build(transcript="Install twelve LED lights")

    result, _events = run(use_case)

    assert result.transcript is not None
    assert result.transcript.text == "Install twelve LED lights"
    assert result.transcript.language == "en"


def test_oversized_audio_is_rejected_before_transcription() -> None:
    """Don't pay to upload something we already know is too big."""
    use_case, transcription, _e, _c = build(max_bytes=10)

    with pytest.raises(AudioTooLargeError):
        run(use_case, audio=b"x" * 5_000)

    assert transcription.calls == []


def test_unsupported_format_is_rejected_before_transcription() -> None:
    use_case, transcription, _e, _c = build()

    with pytest.raises(UnsupportedAudioFormatError):
        run(use_case, mime="application/pdf")

    assert transcription.calls == []


def test_browser_codec_parameter_is_accepted() -> None:
    use_case, transcription, _e, _c = build()

    run(use_case, mime="audio/webm;codecs=opus")

    assert transcription.calls[0][1] == "audio/webm"


def test_silent_recording_fails_clearly() -> None:
    """Better than handing "" to the LLM and getting an invented scope back."""
    use_case, _t, extractor, _c = build(transcript="   ")

    with pytest.raises(TranscriptionError, match="no speech"):
        run(use_case)

    assert extractor.calls == []
