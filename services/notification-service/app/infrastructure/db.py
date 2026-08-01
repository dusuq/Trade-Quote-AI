"""Database engine and tenant-scoped sessions."""

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
def relay_session() -> Iterator[Session]:
    """Yield a session with **no tenant GUC set** — for the outbox relay only.

    Was named `admin_session` and documented as "no RLS tenant scope", which
    was the T205b defect in one sentence: leaving the GUC unset grants no
    bypass. `app_current_tenant()` returns NULL, `tenant_id = NULL` is never
    TRUE, and every RLS-protected table looks empty — silently.

    So this alone is useless to the relay. It is only safe paired with the
    SECURITY DEFINER functions in `0012_notification_outbox_relay.sql`, which
    is the only elevated read this service has. Do not reach for it to "skip
    RLS" anywhere else; it does not do that.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Yield a session scoped to one tenant.

    Sets the transaction-local `app.current_tenant` GUC so Postgres RLS filters
    every query — mirrors esign-service, proposal-service, and quote-service.
    Commits on clean exit so the status update and its outbox event land
    together; rolls back on any error.
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
