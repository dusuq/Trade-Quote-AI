"""Storage port. The application layer depends only on this Protocol, never
on a concrete backend — swap `LocalFileStorage` for an S3-compatible client
later (infra/docker already runs MinIO) without touching use-case code.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class PdfStorage(Protocol):
    def save(self, tenant_id: UUID, key: str, data: bytes) -> str:
        """Persist `data` under `key` (scoped to tenant) and return the storage key."""
        ...

    def read(self, tenant_id: UUID, key: str) -> bytes:
        """Raises PdfNotFoundError if the key doesn't exist for this tenant."""
        ...
