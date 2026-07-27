"""Database engine, tenant-scoped sessions, and the public-link tenant resolver."""

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
    """Yield a session scoped to one tenant.

    Sets the transaction-local `app.current_tenant` GUC so Postgres RLS
    filters every query — mirrors proposal-service and quote-service exactly.
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
    """Resolves which tenant owns a signing token, bypassing RLS for that one
    narrow lookup via a SECURITY DEFINER function (see 0008_esign.sql).

    Necessary because `/v1/sign/{token}` arrives with no tenant context at
    all — a normal query would run with no `app.current_tenant` set and see
    zero rows under RLS.

    Untestable under the SQLite harness (no SECURITY DEFINER), so route tests
    inject `tests.fakes.FakeTenantResolver` instead — the same injectable
    seam proposal-service uses for `resolve_proposal_tenant`.
    """

    def resolve_by_token(self, token: str) -> UUID | None:
        session = SessionLocal()
        try:
            result = session.execute(
                text("SELECT resolve_signature_request_tenant(:tok)"), {"tok": token}
            ).scalar()
            session.commit()
            return UUID(str(result)) if result else None
        finally:
            session.close()
