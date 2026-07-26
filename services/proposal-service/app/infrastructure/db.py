"""Database engine, sessions, multi-tenant RLS context, and the public
view-link tenant resolver."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Yield a database session scoped to a single tenant.
    Sets PostgreSQL GUC `app.current_tenant` (transaction-local) to enable
    RLS row isolation — mirrors quote-service's tenant_session exactly.
    """
    session = SessionLocal()
    try:
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


class PostgresTenantResolver:
    """Resolves which tenant owns a proposal via a SECURITY DEFINER SQL
    function that bypasses RLS for this one lookup — the caller has no
    tenant context yet, so a plain query would see zero rows under RLS.

    Untestable under the SQLite test harness (no SECURITY DEFINER support).
    Route tests inject `tests.fakes.FakeTenantResolver` instead — see
    tests/test_proposal_routes.py. This mirrors T206's pattern of an
    injectable seam around the one piece of logic only live Postgres can
    exercise.
    """

    def resolve(self, proposal_id: UUID) -> UUID | None:
        session = SessionLocal()
        try:
            result = session.execute(
                text("SELECT resolve_proposal_tenant(:pid)"), {"pid": str(proposal_id)}
            ).scalar()
            session.commit()
            return UUID(str(result)) if result else None
        finally:
            session.close()
