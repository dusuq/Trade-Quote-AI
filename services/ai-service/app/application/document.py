"""Document input validation. Pure — no I/O, no SDK.

Mirrors `application/image.py`: OCR documents are photographed the same way
equipment is (a phone photo of a paper invoice, a printed blueprint, or a
handwritten note), so they share the same accepted formats and the same
"cheap rejection before the model call" shape. Kept as its own module rather
than reusing `image.py` directly so the OCR feature can evolve its own limits
(e.g. a future multi-page PDF path) without touching Vision's.
"""

from __future__ import annotations

from app.domain.errors import DocumentTooLargeError, UnsupportedDocumentFormatError

# What Claude's vision API accepts, for a photographed document. Same set as
# `image.py.SUPPORTED_IMAGE_MIME_TYPES` today — OCR input is a photo, not a
# native PDF/DOCX upload.
SUPPORTED_DOCUMENT_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)


def normalize_mime_type(mime_type: str) -> str:
    """Strip parameters and casing, same rule as audio/image uploads."""
    return mime_type.split(";", 1)[0].strip().lower()


def validate_document(
    *,
    size_bytes: int,
    mime_type: str,
    max_bytes: int,
    supported: frozenset[str] = SUPPORTED_DOCUMENT_MIME_TYPES,
) -> str:
    """Validate an upload and return its normalized MIME type.

    Size is checked first: an oversized upload is rejected on the cheaper
    signal without inspecting anything else.
    """
    if size_bytes <= 0:
        raise UnsupportedDocumentFormatError("document file is empty")

    if size_bytes > max_bytes:
        raise DocumentTooLargeError(
            f"document is {size_bytes} bytes; the limit is {max_bytes} bytes"
        )

    normalized = normalize_mime_type(mime_type)
    if normalized not in supported:
        raise UnsupportedDocumentFormatError(
            f"unsupported document format {normalized!r}; supported: {', '.join(sorted(supported))}"
        )
    return normalized
