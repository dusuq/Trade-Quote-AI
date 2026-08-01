"""Pytest fixtures for esign-service."""

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
from tests.fakes import FakeProposalReader, FakeTenantResolver


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite standing in for Postgres.

    `check_same_thread=False` + `StaticPool`: TestClient runs sync route
    handlers on a worker thread while fixtures seed on the main thread, and
    every `:memory:` connection is otherwise its own private database.
    """
    db_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # `tenant_session` issues a Postgres-only `SELECT set_config(...)` to set
    # the RLS GUC. Register a no-op UDF so anything reaching the real helper
    # under SQLite doesn't explode.
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

    Routes call `tenant_session(tenant_id)` directly — there is no FastAPI
    `Depends` to override — so the only injection point is the name as
    imported into `app.interface.routes`. Mirrors quote-service's and
    proposal-service's approach exactly.
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


@pytest.fixture(autouse=True)
def proposals(monkeypatch: pytest.MonkeyPatch) -> FakeProposalReader:
    """Stands in for the synchronous proposal-service read (T204c).

    **autouse deliberately.** Creating a signature request now calls
    proposal-service, and a test that forgot this fixture wouldn't fail
    loudly — it would try to open a real socket to localhost:8005 and hang
    until the timeout. Installing it for every test makes that impossible.
    """
    fake = FakeProposalReader()
    monkeypatch.setattr("app.interface.routes._proposal_reader", fake)
    return fake


@pytest.fixture
def resolver(monkeypatch: pytest.MonkeyPatch) -> FakeTenantResolver:
    """Replaces the SECURITY DEFINER tenant lookup used by public routes."""
    fake = FakeTenantResolver()
    monkeypatch.setattr("app.interface.routes._tenant_resolver", fake)
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


@pytest.fixture
def document_hash() -> str:
    return "a" * 64
