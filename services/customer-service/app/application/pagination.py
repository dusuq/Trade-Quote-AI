"""Pure pagination math — no I/O, directly unit-testable."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Page:
    page: int
    page_size: int
    offset: int
    limit: int


def resolve_page(
    page: int | None, page_size: int | None, *, default_size: int, max_size: int
) -> Page:
    """Clamp raw page/page_size inputs into safe, well-formed values.

    - `page` is 1-indexed and floored at 1.
    - `page_size` is floored at 1 and capped at `max_size`.

    Note: `None` means "not supplied" (use the default); an explicit `0` (or
    negative) is an out-of-range value that floors to 1 — we must not conflate
    the two, so the default is only applied when the input is literally `None`.
    """
    resolved_page = max(1, page if page is not None else 1)
    raw_size = page_size if page_size is not None else default_size
    resolved_size = min(max(1, raw_size), max_size)
    offset = (resolved_page - 1) * resolved_size
    return Page(page=resolved_page, page_size=resolved_size, offset=offset, limit=resolved_size)
