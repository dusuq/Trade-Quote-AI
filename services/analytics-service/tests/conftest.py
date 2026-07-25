import uuid
import pytest
from fastapi.testclient import TestClient
from app.infrastructure.repositories import InMemoryAnalyticsRepository
from app.interface.routes import shared_repo
from app.main import app


@pytest.fixture(autouse=True)
def reset_shared_repo() -> None:
    shared_repo.events.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant_a_id() -> uuid.UUID:
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def tenant_b_id() -> uuid.UUID:
    return uuid.UUID("22222222-2222-2222-2222-222222222222")
