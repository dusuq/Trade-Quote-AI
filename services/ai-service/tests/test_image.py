"""Image upload validation."""

from __future__ import annotations

import pytest

from app.application.image import normalize_mime_type, validate_image
from app.domain.errors import ImageTooLargeError, UnsupportedImageFormatError

MAX = 8 * 1024 * 1024


def test_accepts_a_normal_photo() -> None:
    assert validate_image(size_bytes=1_000, mime_type="image/jpeg", max_bytes=MAX) == "image/jpeg"


def test_strips_parameters() -> None:
    assert normalize_mime_type("image/jpeg; charset=binary") == "image/jpeg"
    assert (
        validate_image(size_bytes=1_000, mime_type="image/jpeg; charset=binary", max_bytes=MAX)
        == "image/jpeg"
    )


def test_rejects_oversized_image() -> None:
    with pytest.raises(ImageTooLargeError):
        validate_image(size_bytes=MAX + 1, mime_type="image/jpeg", max_bytes=MAX)


def test_size_is_checked_before_format() -> None:
    """Reject on the cheaper signal first."""
    with pytest.raises(ImageTooLargeError):
        validate_image(size_bytes=MAX + 1, mime_type="application/zip", max_bytes=MAX)


def test_rejects_unsupported_format() -> None:
    with pytest.raises(UnsupportedImageFormatError):
        validate_image(size_bytes=1_000, mime_type="application/pdf", max_bytes=MAX)


def test_rejects_empty_upload() -> None:
    with pytest.raises(UnsupportedImageFormatError, match="empty"):
        validate_image(size_bytes=0, mime_type="image/jpeg", max_bytes=MAX)


def test_mime_comparison_is_case_insensitive() -> None:
    assert validate_image(size_bytes=10, mime_type="IMAGE/JPEG", max_bytes=MAX) == "image/jpeg"


def test_accepts_png_webp_gif() -> None:
    for mime in ("image/png", "image/webp", "image/gif"):
        assert validate_image(size_bytes=10, mime_type=mime, max_bytes=MAX) == mime
