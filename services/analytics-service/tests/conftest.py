import uuid
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db import Base
from app.infrastructure.repositories import InMemoryAnalyticsRepository
from app.interface.routes import set_test_repository
from app.main import app


@pytest.fixture(autouse=True)
def setup_test_repository() -> Generator[InMemoryAnalyticsRepository, None, None]:
    repo = InMemoryAnalyticsRepository()
    set_test_repository(repo)
    yield repo
    set_test_repository(None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant_a_id() -> uuid.UUID:
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def tenant_b_id() -> uuid.UUID:
    return uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Creates a temporary in-memory SQLite database session for ORM testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
