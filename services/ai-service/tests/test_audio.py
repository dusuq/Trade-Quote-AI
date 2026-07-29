"""Audio upload validation."""

from __future__ import annotations

import pytest

from app.application.audio import normalize_mime_type, validate_audio
from app.domain.errors import AudioTooLargeError, UnsupportedAudioFormatError

MAX = 10 * 1024 * 1024


def test_accepts_a_normal_recording() -> None:
    assert validate_audio(size_bytes=1_000, mime_type="audio/webm", max_bytes=MAX) == "audio/webm"


def test_strips_the_codecs_parameter_browsers_send() -> None:
    """`MediaRecorder` emits `audio/webm;codecs=opus` — rejecting that would
    break every browser recording."""
    assert normalize_mime_type("audio/webm; codecs=opus") == "audio/webm"
    assert (
        validate_audio(size_bytes=1_000, mime_type="audio/webm;codecs=opus", max_bytes=MAX)
        == "audio/webm"
    )


def test_rejects_oversized_audio() -> None:
    with pytest.raises(AudioTooLargeError):
        validate_audio(size_bytes=MAX + 1, mime_type="audio/webm", max_bytes=MAX)


def test_size_is_checked_before_format() -> None:
    """Reject on the cheaper signal first."""
    with pytest.raises(AudioTooLargeError):
        validate_audio(size_bytes=MAX + 1, mime_type="application/zip", max_bytes=MAX)


def test_rejects_unsupported_format() -> None:
    with pytest.raises(UnsupportedAudioFormatError):
        validate_audio(size_bytes=1_000, mime_type="application/pdf", max_bytes=MAX)


def test_rejects_empty_upload() -> None:
    with pytest.raises(UnsupportedAudioFormatError, match="empty"):
        validate_audio(size_bytes=0, mime_type="audio/webm", max_bytes=MAX)


def test_mime_comparison_is_case_insensitive() -> None:
    assert validate_audio(size_bytes=10, mime_type="AUDIO/WEBM", max_bytes=MAX) == "audio/webm"
