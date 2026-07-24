"""Domain-level errors. Interface layer maps these to HTTP status codes."""

from __future__ import annotations


class CustomerNotFoundError(Exception):
    pass


class TagNotFoundError(Exception):
    pass


class InvalidPaginationError(Exception):
    pass
