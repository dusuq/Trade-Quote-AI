"""Pytest fixtures for notification-service."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.models import Base
from app.main import app
from tests.fakes import FakeDependencies


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite standing in for Postgres."""
    db_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # `tenant_session` issues a Postgres-only `SELECT set_config(...)` for the
    # RLS GUC; register a no-op so SQLite doesn't choke on it.
    @event.listens_for(db_engine, "connect")
    def _register_set_config(dbapi_connection, _connection_record):
        dbapi_connection.create_function("set_config", 3, lambda key, value, is_local: value)

    Base.metadata.create_all(bind=db_engine)
    yield db_engine
    Base.metadata.drop_all(bind=db_engine)


@pytest.fixture
def db_session(engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def api_session(engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """Seam letting route tests drive real endpoints against seeded data.

    Routes call `tenant_session(tenant_id)` directly (in the request AND in the
    delivery BackgroundTask), so the one injection point is the name as imported
    into `app.interface.routes`. Both phases share this one session.
    """
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    @contextmanager
    def _override_tenant_session(tenant_id: uuid.UUID) -> Iterator[Session]:
        session.flush()
        yield session

    monkeypatch.setattr("app.interface.routes.tenant_session", _override_tenant_session)

    yield session

    session.rollback()
    session.close()


@pytest.fixture
def fake_deps(monkeypatch: pytest.MonkeyPatch) -> FakeDependencies:
    """Replace the console/HTTP providers with in-memory fakes that record sends."""
    fake = FakeDependencies()
    monkeypatch.setattr("app.interface.routes.deps", fake)
    return fake


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_header(tenant_id: uuid.UUID) -> dict[str, str]:
    return {"x-tenant-id": str(tenant_id), "x-user-id": str(uuid.uuid4())}
