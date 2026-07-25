"""Domain-level errors. Interface layer maps these to HTTP status codes."""

from __future__ import annotations


class PdfRenderError(Exception):
    pass


class PdfNotFoundError(Exception):
    pass
