"""Test harness for payment-service (added in the T303 sign-off).

payment-service shipped with zero tests. This stands up the app against an
in-memory SQLite database with a no-op `set_config` (the RLS GUC is
Postgres-only), the same seam every other service uses.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.models import Base
from app.main import app


@pytest.fixture(scope="session")
def engine():
    db_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # `tenant_session` issues a Postgres-only `SELECT set_config(...)`; register
    # a no-op so it doesn't explode under SQLite.
    @event.listens_for(db_engine, "connect")
    def _register_set_config(dbapi_connection, _record):
        dbapi_connection.create_function(
            "set_config", 3, lambda _k, v, _l: v
        )

    Base.metadata.create_all(bind=db_engine)
    yield db_engine
    Base.metadata.drop_all(bind=db_engine)


@pytest.fixture
def api_session(engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    @contextmanager
    def _override(_tenant_id: uuid.UUID) -> Iterator[Session]:
        session.flush()
        yield session

    monkeypatch.setattr("app.interface.routes.tenant_session", _override)
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_header(tenant_id: uuid.UUID) -> dict[str, str]:
    return {"x-tenant-id": str(tenant_id), "x-user-id": str(uuid.uuid4())}
