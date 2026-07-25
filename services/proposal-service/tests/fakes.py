"""In-memory fake storage implementing app.domain.storage.PdfStorage —
lets the use-case layer be tested with zero filesystem access.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.errors import PdfNotFoundError


class FakePdfStorage:
    def __init__(self) -> None:
        self._data: dict[tuple[UUID, str], bytes] = {}

    def save(self, tenant_id: UUID, key: str, data: bytes) -> str:
        self._data[(tenant_id, key)] = data
        return key

    def read(self, tenant_id: UUID, key: str) -> bytes:
        try:
            return self._data[(tenant_id, key)]
        except KeyError as exc:
            raise PdfNotFoundError(key) from exc
