"""Audio input validation. Pure — no I/O, no SDK."""

from __future__ import annotations

from app.domain.errors import AudioTooLargeError, UnsupportedAudioFormatError

# What Whisper accepts. Checked before upload so an unsupported file fails
# fast and locally instead of costing a round trip and an API error.
SUPPORTED_AUDIO_MIME_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/webm",
        "audio/ogg",
        "video/mp4",
        "video/webm",
    }
)


def normalize_mime_type(mime_type: str) -> str:
    """Strip parameters and casing: `"audio/webm; codecs=opus"` -> `"audio/webm"`.

    Browsers routinely send a codecs parameter on `MediaRecorder` output, so
    comparing the raw header against the allowlist would reject valid audio.
    """
    return mime_type.split(";", 1)[0].strip().lower()


def validate_audio(
    *,
    size_bytes: int,
    mime_type: str,
    max_bytes: int,
    supported: frozenset[str] = SUPPORTED_AUDIO_MIME_TYPES,
) -> str:
    """Validate an upload and return its normalized MIME type.

    Size is checked first: an oversized upload is rejected on the cheaper
    signal without inspecting anything else.
    """
    if size_bytes <= 0:
        raise UnsupportedAudioFormatError("audio file is empty")

    if size_bytes > max_bytes:
        raise AudioTooLargeError(
            f"audio is {size_bytes} bytes; the limit is {max_bytes} bytes"
        )

    normalized = normalize_mime_type(mime_type)
    if normalized not in supported:
        raise UnsupportedAudioFormatError(
            f"unsupported audio format {normalized!r}; supported: {', '.join(sorted(supported))}"
        )
    return normalized
