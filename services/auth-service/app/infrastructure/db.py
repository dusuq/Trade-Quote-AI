"""Database engine/session and the tenant-scoping helper that drives RLS."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Yield a session bound to one tenant. Sets the GUC that RLS policies read,
    so every query in the block is transparently scoped to `tenant_id`.
    """
    session = SessionLocal()
    try:
        # SET LOCAL lives for the transaction; parameterized to avoid injection.
        session.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
