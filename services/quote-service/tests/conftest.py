"""Pytest configuration and fixtures for quote-service."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.models import Base
from app.main import app


@pytest.fixture(scope="session")
def engine():
    # Use SQLite in-memory engine for unit testing database interactions
    db_engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=db_engine)
    yield db_engine
    Base.metadata.drop_all(bind=db_engine)


@pytest.fixture
def db_session(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """Seam that lets a route-level test drive a real endpoint against seeded data.

    Routes call `tenant_session(tenant_id)` directly (there is no FastAPI
    `Depends` to override), so the only injection point is the name as imported
    into `app.interface.routes`. This fixture replaces it with a context manager
    yielding a session bound to a throwaway in-memory SQLite database, and hands
    that same session to the test for seeding.

    Two engine options are load-bearing rather than incidental:

    * `check_same_thread: False` — `TestClient` runs a *sync* endpoint on a
      worker thread, so the connection opened while seeding on the main thread
      would otherwise be rejected when the handler touches it.
    * `StaticPool` — every `:memory:` connection is its own private database, so
      without a single pooled connection the handler would query an empty schema
      and see none of the seeded rows.

    Yielding one shared session also means seeded flushes are visible to the
    handler without committing, and teardown rolls everything back.
    """
    db_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=db_engine)
    session_factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = session_factory()

    @contextmanager
    def _override_tenant_session(tenant_id: uuid.UUID) -> Iterator[Session]:
        session.flush()
        yield session

    monkeypatch.setattr("app.interface.routes.tenant_session", _override_tenant_session)

    yield session

    session.rollback()
    session.close()
    db_engine.dispose()


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def customer_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_header(tenant_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-tenant-id": str(tenant_id),
        "x-user-id": str(uuid.uuid4()),
    }
