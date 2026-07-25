"""Local-disk implementation of the PdfStorage port — used for MVP/dev and
in tests. Swap for an S3-compatible client (infra/docker runs MinIO) once
object storage is wired; the Protocol in app.domain.storage is the seam.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.domain.errors import PdfNotFoundError


class LocalFileStorage:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def _path(self, tenant_id: UUID, key: str) -> Path:
        # Tenant-scoped directory so files never collide or leak across tenants.
        return self._base / str(tenant_id) / key

    def save(self, tenant_id: UUID, key: str, data: bytes) -> str:
        path = self._path(tenant_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, tenant_id: UUID, key: str) -> bytes:
        path = self._path(tenant_id, key)
        if not path.is_file():
            raise PdfNotFoundError(key)
        return path.read_bytes()
