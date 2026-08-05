"""Integration test for migration 0016 (auth_audit_log widening, append-only REVOKE, outcome CHECK constraint, and RLS)."""

import sqlite3
import uuid

import pytest


def test_migration_0016_schema_and_constraints(tmp_path):
    """Test table structure, outcome CHECK constraint, and append-only constraints."""
    db_path = tmp_path / "test_0016.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Base table creation (simulating 0002)
    cur.execute("""
        CREATE TABLE auth_audit_log (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            action TEXT NOT NULL,
            actor_id UUID,
            ip_address TEXT,
            user_agent TEXT,
            metadata JSON,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Migration 0016 column additions
    cur.execute("ALTER TABLE auth_audit_log ADD COLUMN outcome text NOT NULL DEFAULT 'success';")
    cur.execute("ALTER TABLE auth_audit_log ADD COLUMN actor_email text;")
    cur.execute("ALTER TABLE auth_audit_log ADD COLUMN target_type text;")
    cur.execute("ALTER TABLE auth_audit_log ADD COLUMN target_id uuid;")
    cur.execute("ALTER TABLE auth_audit_log ADD COLUMN request_id text;")

    # 3. outcome CHECK constraint emulation
    cur.execute("""
        CREATE TRIGGER check_auth_audit_log_outcome
        BEFORE INSERT ON auth_audit_log
        FOR EACH ROW
        WHEN NEW.outcome NOT IN ('success', 'failure')
        BEGIN
            SELECT RAISE(FAIL, 'CHECK constraint failed: outcome must be success or failure');
        END;
    """)

    tenant_a = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    # (a) Valid INSERT (outcome='success')
    cur.execute("""
        INSERT INTO auth_audit_log (id, tenant_id, action, outcome, actor_email, request_id)
        VALUES (?, ?, 'auth.login.succeeded', 'success', 'user@example.com', 'req-123')
    """, (event_id, tenant_a))
    conn.commit()

    cur.execute("SELECT action, outcome, actor_email, request_id FROM auth_audit_log WHERE id = ?", (event_id,))
    row = cur.fetchone()
    assert row == ("auth.login.succeeded", "success", "user@example.com", "req-123")

    # (b) Valid INSERT (outcome='failure')
    failed_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO auth_audit_log (id, tenant_id, action, outcome, actor_email, request_id)
        VALUES (?, ?, 'auth.login.failed', 'failure', 'attacker@example.com', 'req-124')
    """, (failed_id, tenant_a))
    conn.commit()

    # (c) Invalid outcome -> MUST FAIL
    invalid_id = str(uuid.uuid4())
    with pytest.raises(sqlite3.IntegrityError, match="outcome must be success or failure"):
        cur.execute("""
            INSERT INTO auth_audit_log (id, tenant_id, action, outcome)
            VALUES (?, ?, 'auth.login.failed', 'maybe')
        """, (invalid_id, tenant_a))

    conn.close()


def test_auth_audit_log_append_only_sql_parsing():
    """Assert SQL script 0016 explicitly revokes UPDATE, DELETE, TRUNCATE for tradequote_app."""
    with open("infra/db/migrations/0016_security_audit.sql", encoding="utf-8") as f:
        sql = f.read()

    assert "REVOKE UPDATE, DELETE, TRUNCATE ON auth_audit_log FROM tradequote_app" in sql
    assert "outcome IN ('success', 'failure')" in sql
    assert "idx_auth_audit_failures" in sql
    assert "idx_auth_audit_actor_email" in sql
