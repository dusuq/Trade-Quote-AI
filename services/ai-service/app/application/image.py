"""Image input validation. Pure — no I/O, no SDK."""

from __future__ import annotations

from app.domain.errors import ImageTooLargeError, UnsupportedImageFormatError

# What Claude's vision API accepts. Checked before upload so an unsupported
# file fails fast and locally instead of costing a round trip and an API
# error (mirrors application/audio.py's SUPPORTED_AUDIO_MIME_TYPES).
SUPPORTED_IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)


def normalize_mime_type(mime_type: str) -> str:
    """Strip parameters and casing, same rule as audio uploads."""
    return mime_type.split(";", 1)[0].strip().lower()


def validate_image(
    *,
    size_bytes: int,
    mime_type: str,
    max_bytes: int,
    supported: frozenset[str] = SUPPORTED_IMAGE_MIME_TYPES,
) -> str:
    """Validate an upload and return its normalized MIME type.

    Size is checked first: an oversized upload is rejected on the cheaper
    signal without inspecting anything else.
    """
    if size_bytes <= 0:
        raise UnsupportedImageFormatError("image file is empty")

    if size_bytes > max_bytes:
        raise ImageTooLargeError(
            f"image is {size_bytes} bytes; the limit is {max_bytes} bytes"
        )

    normalized = normalize_mime_type(mime_type)
    if normalized not in supported:
        raise UnsupportedImageFormatError(
            f"unsupported image format {normalized!r}; supported: {', '.join(sorted(supported))}"
        )
    return normalized
