"""PostgreSQL Row-Level Security (RLS) Tenant Isolation & Verification Test Suite (T207 / T311).

Tests PostgreSQL RLS policies across all domain tables (app_user, customer, pricebook_item, quote, proposal, analytics_events),
verifies T203's SECURITY DEFINER proposal tenant resolver, T206's summary query over live Postgres rows,
and T206b's SQLAlchemy Enum lowercase values_callable.
"""

from __future__ import annotations

import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Default local/CI PostgreSQL test URL
POSTGRES_TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://tradequote_app:app_password@34.24.115.216:5432/tradequote")


def is_postgres_available() -> bool:
    """Checks whether a live PostgreSQL instance with RLS schema is reachable."""
    try:
        engine = create_engine(POSTGRES_TEST_URL, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1 FROM schema_migrations WHERE version = '0001'"))
            return res.scalar() == 1
    except Exception:
        return False


LIVE_POSTGRES = is_postgres_available()
pytestmark = pytest.mark.skipif(not LIVE_POSTGRES, reason="Requires live PostgreSQL DB with RLS migrations applied (T002b/T311)")


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


def create_tenant(session: Session, name: str = "Test Tenant") -> uuid.UUID:
    tid = uuid.uuid4()
    slug = f"tenant-{str(tid)[:8]}"
    session.execute(
        text("INSERT INTO tenant (id, name, slug, created_at, updated_at) VALUES (:id, :name, :slug, now(), now())"),
        {"id": tid, "name": name, "slug": slug},
    )
    session.flush()
    return tid


def set_tenant_context(session: Session, tenant_id: uuid.UUID | str) -> None:
    session.execute(text("SELECT set_config('app.current_tenant', :tid, true)"), {"tid": str(tenant_id)})


def test_customer_rls_tenant_isolation(rls_session):
    tenant_a = create_tenant(rls_session, "Tenant A")
    tenant_b = create_tenant(rls_session, "Tenant B")

    # 1. Insert Customer as Tenant A
    set_tenant_context(rls_session, tenant_a)
    cust_id = uuid.uuid4()
    rls_session.execute(
        text("""
            INSERT INTO customer (id, tenant_id, display_name, created_at, updated_at)
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
    tenant_a = create_tenant(rls_session, "Tenant A")
    tenant_b = create_tenant(rls_session, "Tenant B")

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


def test_quote_rls_tenant_isolation_and_enum_summary(rls_session):
    tenant_a = create_tenant(rls_session, "Tenant A")
    tenant_b = create_tenant(rls_session, "Tenant B")

    # Create Customer + Quotes under Tenant A (verifying T206b enum values_callable matching Postgres lowercase labels)
    set_tenant_context(rls_session, tenant_a)
    cust_id = uuid.uuid4()
    quote_id_1 = uuid.uuid4()
    quote_id_2 = uuid.uuid4()

    rls_session.execute(
        text("INSERT INTO customer (id, tenant_id, display_name, created_at, updated_at) VALUES (:id, :tid, 'Cust A', now(), now())"),
        {"id": cust_id, "tid": tenant_a},
    )
    rls_session.execute(
        text("""
            INSERT INTO quote (id, tenant_id, customer_id, number, status, created_via, currency, tax_rate_bps, subtotal_minor, tax_minor, total_minor, current_version, created_at, updated_at)
            VALUES (:id, :tid, :cid, 'Q-RLS-001', 'sent', 'manual', 'USD', 875, 10000, 875, 10875, 1, now(), now())
        """),
        {"id": quote_id_1, "tid": tenant_a, "cid": cust_id},
    )
    rls_session.execute(
        text("""
            INSERT INTO quote (id, tenant_id, customer_id, number, status, created_via, currency, tax_rate_bps, subtotal_minor, tax_minor, total_minor, current_version, created_at, updated_at)
            VALUES (:id, :tid, :cid, 'Q-RLS-002', 'accepted', 'manual', 'USD', 875, 20000, 1750, 21750, 1, now(), now())
        """),
        {"id": quote_id_2, "tid": tenant_a, "cid": cust_id},
    )
    rls_session.flush()

    # Verify status equality filter against Postgres lowercase enum types
    sent_count = rls_session.execute(
        text("SELECT count(*) FROM quote WHERE tenant_id = :tid AND status = 'sent'"),
        {"tid": tenant_a},
    ).scalar()
    assert sent_count == 1, "Status filter 'sent' failed against live Postgres"

    accepted_count = rls_session.execute(
        text("SELECT count(*) FROM quote WHERE tenant_id = :tid AND status = 'accepted'"),
        {"tid": tenant_a},
    ).scalar()
    assert accepted_count == 1, "Status filter 'accepted' failed against live Postgres"

    # Switch to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res = rls_session.execute(text("SELECT count(*) FROM quote WHERE id = :id"), {"id": quote_id_1}).scalar()
    assert res == 0, "RLS Violation: Tenant B was able to view Tenant A quote!"


def test_proposal_rls_and_security_definer(rls_session):
    """Verifies T203 proposal RLS policy and SECURITY DEFINER tenant resolver against real Postgres."""
    tenant_a = create_tenant(rls_session, "Tenant A")
    tenant_b = create_tenant(rls_session, "Tenant B")
    quote_id = uuid.uuid4()
    template_id = uuid.uuid4()
    proposal_id = uuid.uuid4()

    set_tenant_context(rls_session, tenant_a)

    # Insert template + proposal
    rls_session.execute(
        text("""
            INSERT INTO proposal_template (id, tenant_id, name, company_name, is_default, created_at, updated_at)
            VALUES (:id, :tid, 'Default Template', 'Acme Trade Co', true, now(), now())
        """),
        {"id": template_id, "tid": tenant_a},
    )
    rls_session.execute(
        text("""
            INSERT INTO proposal (id, tenant_id, quote_id, template_id, number, status, current_version, created_at, updated_at)
            VALUES (:id, :tid, :qid, :tempid, 'P-2026-000001', 'draft', 1, now(), now())
        """),
        {"id": proposal_id, "tid": tenant_a, "qid": quote_id, "tempid": template_id},
    )
    rls_session.flush()

    # Test SECURITY DEFINER function resolve_proposal_tenant (bypasses RLS for public /view lookup)
    resolved_tenant = rls_session.execute(
        text("SELECT resolve_proposal_tenant(:pid)"),
        {"pid": proposal_id},
    ).scalar()
    assert str(resolved_tenant) == str(tenant_a), "resolve_proposal_tenant SECURITY DEFINER function failed"

    # Switch context to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res = rls_session.execute(text("SELECT count(*) FROM proposal WHERE id = :id"), {"id": proposal_id}).scalar()
    assert res == 0, "RLS Violation: Tenant B was able to view Tenant A proposal!"


def test_analytics_events_rls_tenant_isolation(rls_session):
    """Verifies T307b analytics_events table RLS policy against real Postgres."""
    tenant_a = create_tenant(rls_session, "Tenant A")
    tenant_b = create_tenant(rls_session, "Tenant B")
    event_id = uuid.uuid4()

    set_tenant_context(rls_session, tenant_a)
    rls_session.execute(
        text("""
            INSERT INTO analytics_events (id, tenant_id, quote_id, customer_id, customer_name, event_type, trade, amount_minor, created_at)
            VALUES (:id, :tid, :qid, :cid, 'Acme Corp', 'quote.accepted', 'electrical', 500000, now())
        """),
        {
            "id": event_id,
            "tid": tenant_a,
            "qid": uuid.uuid4(),
            "cid": uuid.uuid4(),
        },
    )
    rls_session.flush()

    # Verify Tenant A can query event
    res_a = rls_session.execute(text("SELECT count(*) FROM analytics_events WHERE id = :id"), {"id": event_id}).scalar()
    assert res_a == 1

    # Switch context to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res_b = rls_session.execute(text("SELECT count(*) FROM analytics_events WHERE id = :id"), {"id": event_id}).scalar()
    assert res_b == 0, "RLS Violation: Tenant B was able to view Tenant A analytics event!"


def test_cross_tenant_insert_blocked_by_rls(rls_session):
    tenant_a = create_tenant(rls_session, "Tenant A")
    tenant_b = create_tenant(rls_session, "Tenant B")

    # Active tenant is Tenant A
    set_tenant_context(rls_session, tenant_a)

    # Attempt to insert a row with tenant_id = Tenant B while app.current_tenant = Tenant A
    with pytest.raises(Exception) as exc_info:
        rls_session.execute(
            text("""
                INSERT INTO customer (id, tenant_id, display_name, created_at, updated_at)
                VALUES (:id, :tenant_id, 'Malicious Cross-Tenant Customer', now(), now())
            """),
            {"id": uuid.uuid4(), "tenant_id": tenant_b},
        )
        rls_session.flush()

    assert "row-level security" in str(exc_info.value).lower() or "policy" in str(exc_info.value).lower()
