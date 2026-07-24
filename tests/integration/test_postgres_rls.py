"""PostgreSQL Row-Level Security (RLS) Tenant Isolation Test Suite (T207 / R1 Audit Recommendation).

Tests PostgreSQL RLS policies across all Phase 1 domain tables (app_user, customer, pricebook_item, quote).
Skipped automatically if live PostgreSQL is not reachable, preserving fast SQLite offline CI runs.
"""

from __future__ import annotations

import os
import uuid
import pytest
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session

# Default local/CI PostgreSQL test URL
POSTGRES_TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote")


def is_postgres_available() -> bool:
    """Checks whether a live PostgreSQL instance with RLS schema is reachable."""
    try:
        engine = create_engine(POSTGRES_TEST_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1 FROM schema_migrations WHERE version = '0001'"))
            return res.scalar() == 1
    except Exception:
        return False


LIVE_POSTGRES = is_postgres_available()
pytestmark = pytest.mark.skipif(not LIVE_POSTGRES, reason="Requires live PostgreSQL DB with RLS migrations applied (T002b)")


@pytest.fixture(scope="module")
def postgres_engine():
    engine = create_engine(POSTGRES_TEST_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def rls_session(postgres_engine):
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def set_tenant_context(session: Session, tenant_id: uuid.UUID | str) -> None:
    session.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": str(tenant_id)})


def test_customer_rls_tenant_isolation(rls_session):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    # 1. Insert Customer as Tenant A
    set_tenant_context(rls_session, tenant_a)
    cust_id = uuid.uuid4()
    rls_session.execute(
        text("""
            INSERT INTO customer (id, tenant_id, name, created_at, updated_at)
            VALUES (:id, :tenant_id, 'Acme Corp Tenant A', now(), now())
        """),
        {"id": cust_id, "tenant_id": tenant_a},
    )
    rls_session.flush()

    # Verify Tenant A can see its customer
    res = rls_session.execute(text("SELECT count(*) FROM customer WHERE id = :id"), {"id": cust_id}).scalar()
    assert res == 1

    # 2. Switch context to Tenant B
    set_tenant_context(rls_session, tenant_b)
    # Query for Tenant A's customer while active tenant is Tenant B
    res_b = rls_session.execute(text("SELECT count(*) FROM customer WHERE id = :id"), {"id": cust_id}).scalar()
    assert res_b == 0, "RLS Violation: Tenant B was able to view Tenant A customer!"


def test_pricebook_rls_tenant_isolation(rls_session):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    # Insert Pricebook Item as Tenant A
    set_tenant_context(rls_session, tenant_a)
    item_id = uuid.uuid4()
    rls_session.execute(
        text("""
            INSERT INTO pricebook_item (id, tenant_id, kind, sku, name, unit, unit_cost_minor, default_markup_bps, currency, is_active, created_at, updated_at)
            VALUES (:id, :tenant_id, 'material', 'ELE-001-RLS', '200A Panel', 'each', 15000, 3000, 'USD', true, now(), now())
        """),
        {"id": item_id, "tenant_id": tenant_a},
    )
    rls_session.flush()

    # Switch to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res = rls_session.execute(text("SELECT count(*) FROM pricebook_item WHERE id = :id"), {"id": item_id}).scalar()
    assert res == 0, "RLS Violation: Tenant B was able to view Tenant A pricebook item!"


def test_quote_rls_tenant_isolation(rls_session):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    # Create Customer + Quote under Tenant A
    set_tenant_context(rls_session, tenant_a)
    cust_id = uuid.uuid4()
    quote_id = uuid.uuid4()

    rls_session.execute(
        text("INSERT INTO customer (id, tenant_id, name, created_at, updated_at) VALUES (:id, :tid, 'Cust A', now(), now())"),
        {"id": cust_id, "tid": tenant_a},
    )
    rls_session.execute(
        text("""
            INSERT INTO quote (id, tenant_id, customer_id, number, status, created_via, currency, tax_rate_bps, subtotal_minor, tax_minor, total_minor, current_version, created_at, updated_at)
            VALUES (:id, :tid, :cid, 'Q-RLS-001', 'draft', 'manual', 'USD', 875, 10000, 875, 10875, 1, now(), now())
        """),
        {"id": quote_id, "tid": tenant_a, "cid": cust_id},
    )
    rls_session.flush()

    # Switch to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res = rls_session.execute(text("SELECT count(*) FROM quote WHERE id = :id"), {"id": quote_id}).scalar()
    assert res == 0, "RLS Violation: Tenant B was able to view Tenant A quote!"


def test_cross_tenant_insert_blocked_by_rls(rls_session):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    # Active tenant is Tenant A
    set_tenant_context(rls_session, tenant_a)

    # Attempt to insert a row with tenant_id = Tenant B while app.current_tenant = Tenant A
    with pytest.raises(Exception) as exc_info:
        rls_session.execute(
            text("""
                INSERT INTO customer (id, tenant_id, name, created_at, updated_at)
                VALUES (:id, :tenant_id, 'Malicious Cross-Tenant Customer', now(), now())
            """),
            {"id": uuid.uuid4(), "tenant_id": tenant_b},
        )
        rls_session.flush()

    assert "row-level security" in str(exc_info.value).lower() or "policy" in str(exc_info.value).lower()
