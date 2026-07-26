"""Pytest configuration and fixtures for proposal-service."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.entities import (
    CompanyBranding,
    CustomerInfo,
    Money,
    ProposalDocument,
    ProposalLineItem,
)
from app.infrastructure.models import Base
from app.main import app


@pytest.fixture(scope="session")
def engine():
    # check_same_thread=False + StaticPool: TestClient runs route handlers on a
    # worker thread, but db_session (and the SessionLocal it's monkeypatched onto
    # in test_proposal_routes.py) is created on the main test thread. Without
    # these, the public /view route test fails with sqlite3.ProgrammingError
    # ("SQLite objects created in a thread can only be used in that same thread") —
    # mirrors quote-service's tests/conftest.py::api_session engine.
    db_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # `tenant_session` (app/infrastructure/db.py) issues a Postgres-only
    # `SELECT set_config(...)` to set the RLS GUC. SQLite has no such function;
    # register a no-op UDF so route tests that go through tenant_session (the
    # public /view route) don't need a real Postgres instance.
    @event.listens_for(db_engine, "connect")
    def _register_set_config(dbapi_connection, _connection_record):
        dbapi_connection.create_function(
            "set_config", 3, lambda key, value, is_local: value
        )

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
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_header(tenant_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-tenant-id": str(tenant_id),
        "x-user-id": str(uuid.uuid4()),
    }


@pytest.fixture
def sample_document() -> ProposalDocument:
    return ProposalDocument(
        proposal_id=uuid.uuid4(),
        quote_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        branding=CompanyBranding(
            company_name="Bright Sparks Electric",
            primary_color="#1D4ED8",
            phone="(555) 123-4567",
            email="hello@brightsparks.example",
            website="brightsparks.example",
        ),
        customer=CustomerInfo(
            display_name="Jordan Rivera",
            email="jordan@example.com",
            phone="(555) 987-6543",
            property_address="742 Evergreen Terrace, Springfield",
        ),
        line_items=[
            ProposalLineItem(
                description="Replace 200A panel",
                quantity=1,
                unit="each",
                unit_price=Money(85000, "USD"),
                line_total=Money(85000, "USD"),
            ),
            ProposalLineItem(
                description="Install LED recessed lights",
                quantity=12,
                unit="each",
                unit_price=Money(4500, "USD"),
                line_total=Money(54000, "USD"),
            ),
        ],
        subtotal=Money(139000, "USD"),
        tax=Money(12160, "USD"),
        total=Money(151160, "USD"),
        scope_of_work="Replace the main electrical panel and install 12 LED recessed lights "
        "throughout the living room and kitchen.",
        warranty_text="All labor is warrantied for 2 years from the completion date.",
        terms_text="50% deposit due at signing, balance due on completion.",
        valid_until="2026-08-15",
        qr_payload_url="https://tradequote.example/p/view",
    )
