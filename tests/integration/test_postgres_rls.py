"""PostgreSQL Row-Level Security (RLS) Tenant Isolation & Verification Test Suite (T207 / T311 / T311b).

Tests PostgreSQL RLS policies across domain tables (app_user, customer, pricebook_item, quote, proposal, analytics_events, ai_usage_log),
verifies T203's SECURITY DEFINER proposal tenant resolver and proposal lifecycle,
exercises T206's summary query and timezone boundaries over live Postgres rows,
and verifies T206b's SQLAlchemy Enum lowercase values_callable ORM round-trip.
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUOTE_PATH = str(REPO_ROOT / "services" / "quote-service")
PROPOSAL_PATH = str(REPO_ROOT / "services" / "proposal-service")

# 1. Load quote-service models and summary application logic
sys.path.insert(0, QUOTE_PATH)
from app.application.summary import resolve_range, summarize_quotes  # noqa: E402
from app.domain.models import QuoteCreatedVia, QuoteModel, QuoteStatus  # noqa: E402

sys.path.remove(QUOTE_PATH)

# Clear app module cache before loading proposal-service
for m in list(sys.modules):
    if m == "app" or m.startswith("app."):
        del sys.modules[m]

# 2. Load proposal-service models
sys.path.insert(0, PROPOSAL_PATH)
from app.domain.proposal import ProposalStatus as ProposalStatusEnum  # noqa: E402
from app.infrastructure.models import ProposalModel, ProposalTemplateModel  # noqa: E402

sys.path.remove(PROPOSAL_PATH)

# Default local/CI PostgreSQL test URL (no committed live credentials or public IPs)
POSTGRES_TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://tradequote_app:app_password@localhost:5432/tradequote",
)


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
pytestmark = pytest.mark.skipif(
    not LIVE_POSTGRES,
    reason="Requires live PostgreSQL DB with RLS migrations applied (T002b/T311/T311b)",
)


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


def test_customer_rls_tenant_isolation(rls_session: Session):
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
    res_b = rls_session.execute(text("SELECT count(*) FROM customer WHERE id = :id"), {"id": cust_id}).scalar()
    assert res_b == 0, "RLS Violation: Tenant B was able to view Tenant A customer!"


def test_pricebook_rls_tenant_isolation(rls_session: Session):
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


def test_quote_rls_tenant_isolation(rls_session: Session):
    tenant_a = create_tenant(rls_session, "Tenant A")
    tenant_b = create_tenant(rls_session, "Tenant B")

    set_tenant_context(rls_session, tenant_a)
    cust_id = uuid.uuid4()
    quote_id = uuid.uuid4()

    rls_session.execute(
        text("INSERT INTO customer (id, tenant_id, display_name, created_at, updated_at) VALUES (:id, :tid, 'Cust A', now(), now())"),
        {"id": cust_id, "tid": tenant_a},
    )
    rls_session.execute(
        text("""
            INSERT INTO quote (id, tenant_id, customer_id, number, status, created_via, currency, tax_rate_bps, subtotal_minor, tax_minor, total_minor, current_version, created_at, updated_at)
            VALUES (:id, :tid, :cid, 'Q-RLS-001', 'sent', 'manual', 'USD', 875, 10000, 875, 10875, 1, now(), now())
        """),
        {"id": quote_id, "tid": tenant_a, "cid": cust_id},
    )
    rls_session.flush()

    # Switch to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res = rls_session.execute(text("SELECT count(*) FROM quote WHERE id = :id"), {"id": quote_id}).scalar()
    assert res == 0, "RLS Violation: Tenant B was able to view Tenant A quote!"


def test_quote_status_orm_roundtrip_and_summary(rls_session: Session):
    """Verifies T206b enum values_callable ORM round-trip and T206 summary calculation with timezone bounds over Postgres."""
    tenant_a = create_tenant(rls_session, "Tenant A (ORM)")
    set_tenant_context(rls_session, tenant_a)

    cust_id = uuid.uuid4()
    rls_session.execute(
        text("INSERT INTO customer (id, tenant_id, display_name, created_at, updated_at) VALUES (:id, :tid, 'Cust ORM', now(), now())"),
        {"id": cust_id, "tid": tenant_a},
    )
    rls_session.flush()

    # 1. Write Quote via SQLAlchemy ORM (T206b verification)
    quote_sent = QuoteModel(
        id=uuid.uuid4(),
        tenant_id=tenant_a,
        customer_id=cust_id,
        number="Q-ORM-001",
        status=QuoteStatus.SENT,
        created_via=QuoteCreatedVia.MANUAL,
        currency="USD",
        tax_rate_bps=875,
        subtotal_minor=10000,
        tax_minor=875,
        total_minor=10875,
    )
    quote_accepted = QuoteModel(
        id=uuid.uuid4(),
        tenant_id=tenant_a,
        customer_id=cust_id,
        number="Q-ORM-002",
        status=QuoteStatus.ACCEPTED,
        created_via=QuoteCreatedVia.MANUAL,
        currency="USD",
        tax_rate_bps=875,
        subtotal_minor=20000,
        tax_minor=1750,
        total_minor=21750,
    )
    quote_draft = QuoteModel(
        id=uuid.uuid4(),
        tenant_id=tenant_a,
        customer_id=cust_id,
        number="Q-ORM-003",
        status=QuoteStatus.DRAFT,
        created_via=QuoteCreatedVia.MANUAL,
        currency="USD",
        tax_rate_bps=875,
        subtotal_minor=5000,
        tax_minor=437,
        total_minor=5437,
    )
    rls_session.add_all([quote_sent, quote_accepted, quote_draft])
    rls_session.flush()

    # Assert Postgres raw string label is lowercase 'sent' (T206b fix check)
    raw_status = rls_session.execute(
        text("SELECT status::text FROM quote WHERE id = :id"),
        {"id": quote_sent.id},
    ).scalar()
    assert raw_status == "sent", f"Stored Postgres enum string label was {raw_status!r}, expected 'sent'"

    # Assert ORM query returns QuoteStatus.SENT
    orm_quote = rls_session.query(QuoteModel).filter(QuoteModel.id == quote_sent.id).first()
    assert orm_quote is not None
    assert orm_quote.status == QuoteStatus.SENT

    # 2. Exercise summarize_quotes() + resolve_range() (T206 verification)
    now_utc = datetime.now(UTC)
    bounds = resolve_range("America/New_York", "mtd", now=now_utc)
    summary = summarize_quotes(rls_session, tenant_a, bounds)

    assert summary.quotes_today == 3
    assert summary.pending_count == 1  # 1 SENT
    assert summary.accepted_count == 1  # 1 ACCEPTED
    assert summary.decided_count == 1  # 1 ACCEPTED
    assert len(summary.totals) == 1
    assert summary.totals[0].currency == "USD"
    # Verify integer coercion from Postgres numeric sum
    assert isinstance(summary.totals[0].accepted_value_minor, int)
    assert summary.totals[0].accepted_value_minor == 21750


def test_proposal_lifecycle_and_security_definer(rls_session: Session):
    """Verifies T203 proposal ORM lifecycle and SECURITY DEFINER tenant resolver against real Postgres."""
    tenant_a = create_tenant(rls_session, "Tenant A (Proposal)")
    tenant_b = create_tenant(rls_session, "Tenant B (Proposal)")
    quote_id = uuid.uuid4()
    template_id = uuid.uuid4()
    proposal_id = uuid.uuid4()

    set_tenant_context(rls_session, tenant_a)

    # Insert template + proposal via ORM
    template = ProposalTemplateModel(
        id=template_id,
        tenant_id=tenant_a,
        name="Default Template",
        company_name="Acme Trade Co",
        is_default=True,
    )
    proposal = ProposalModel(
        id=proposal_id,
        tenant_id=tenant_a,
        quote_id=quote_id,
        template_id=template_id,
        number="P-2026-000001",
        status=ProposalStatusEnum.DRAFT,
    )
    rls_session.add_all([template, proposal])
    rls_session.flush()

    # Test SECURITY DEFINER function resolve_proposal_tenant
    resolved_tenant = rls_session.execute(
        text("SELECT resolve_proposal_tenant(:pid)"),
        {"pid": proposal_id},
    ).scalar()
    assert str(resolved_tenant) == str(tenant_a), "resolve_proposal_tenant SECURITY DEFINER function failed"

    # Transition proposal to SENT
    proposal.status = ProposalStatusEnum.SENT
    proposal.sent_at = datetime.now(UTC)
    rls_session.flush()

    raw_proposal_status = rls_session.execute(
        text("SELECT status::text FROM proposal WHERE id = :id"),
        {"id": proposal_id},
    ).scalar()
    assert raw_proposal_status == "sent"

    # Switch context to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res = rls_session.query(ProposalModel).filter(ProposalModel.id == proposal_id).first()
    assert res is None, "RLS Violation: Tenant B was able to view Tenant A proposal via ORM!"


def test_analytics_events_rls_tenant_isolation(rls_session: Session):
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


def test_ai_usage_log_rls_tenant_isolation(rls_session: Session):
    """Verifies T201 ai_usage_log table RLS policy against real Postgres."""
    tenant_a = create_tenant(rls_session, "Tenant A (AI)")
    tenant_b = create_tenant(rls_session, "Tenant B (AI)")
    usage_id = uuid.uuid4()

    set_tenant_context(rls_session, tenant_a)
    rls_session.execute(
        text("""
            INSERT INTO ai_usage_log (id, tenant_id, feature, model_id, input_kind, tokens_used, cost_minor, created_at)
            VALUES (:id, :tid, 'voice', 'whisper-1', 'voice', 450, 15, now())
        """),
        {
            "id": usage_id,
            "tid": tenant_a,
        },
    )
    rls_session.flush()

    # Verify Tenant A can query ai_usage_log
    res_a = rls_session.execute(text("SELECT count(*) FROM ai_usage_log WHERE id = :id"), {"id": usage_id}).scalar()
    assert res_a == 1

    # Switch context to Tenant B
    set_tenant_context(rls_session, tenant_b)
    res_b = rls_session.execute(text("SELECT count(*) FROM ai_usage_log WHERE id = :id"), {"id": usage_id}).scalar()
    assert res_b == 0, "RLS Violation: Tenant B was able to view Tenant A ai_usage_log row!"


def test_cross_tenant_insert_blocked_by_rls(rls_session: Session):
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
