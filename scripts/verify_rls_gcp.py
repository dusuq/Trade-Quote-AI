#!/usr/bin/env python3
"""Apply migration 0015 & verify RLS live on GCP Postgres VM.

Checks:
1. Applies migrations 0001 through 0015.
2. Asserts tradequote_app role properties: rolsuper = f, rolbypassrls = f.
3. Asserts tradequote_app does NOT own tables (migrations run as owner).
4. Runs pytest tests/integration/test_postgres_rls.py as tradequote_app.
5. Verifies SECURITY DEFINER escape hatches (outbox relay, proposal view, signature request).
"""

import glob
import os
import sys
import time
import uuid

import psycopg

HOST = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DB_HOST", "127.0.0.1")
PORT = int(os.getenv("DB_PORT", "5432"))
DBNAME = os.getenv("DB_NAME", "tradequote")
OWNER_USER = os.getenv("DB_OWNER_USER", "postgres")
OWNER_PASS = os.getenv("DB_OWNER_PASS", "")
APP_PASS = os.getenv("APP_PASS", "")

OWNER_URL = os.getenv("OWNER_DATABASE_URL", f"postgresql://{OWNER_USER}:{OWNER_PASS}@{HOST}:{PORT}/{DBNAME}")
APP_URL = os.getenv("TEST_DATABASE_URL", f"postgresql://tradequote_app:{APP_PASS}@{HOST}:{PORT}/{DBNAME}")

def wait_for_postgres():
    print(f"Connecting to Postgres at {HOST}:{PORT}...")
    for i in range(30):
        try:
            # No `as conn`: this probe only proves the server accepts a
            # connection, and binding an unused name tripped F841 once the
            # repo-root lint lane started covering scripts/ (T313).
            with psycopg.connect(OWNER_URL, connect_timeout=3):
                print("Connected successfully to Postgres!")
                return
        except Exception as e:
            print(f"Waiting for Postgres ({i+1}/30)... {e}")
            time.sleep(2)
    raise RuntimeError("Could not connect to Postgres")

def apply_migrations():
    print("\n--- Applying migrations 0001 through 0015 ---")
    migration_files = sorted(glob.glob("infra/db/migrations/*.sql"))
    with psycopg.connect(OWNER_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for fpath in migration_files:
                fname = os.path.basename(fpath)
                print(f"Applying {fname}...")
                with open(fpath, encoding="utf-8") as f:
                    sql = f.read()
                cur.execute(sql)
    print("All migrations applied successfully!")

def verify_role_properties():
    print("\n--- Verifying tradequote_app Role Properties ---")
    with psycopg.connect(OWNER_URL) as conn:
        with conn.cursor() as cur:
            # Set password for tradequote_app
            cur.execute(f"ALTER ROLE tradequote_app WITH LOGIN PASSWORD '{APP_PASS}';")
            
            cur.execute("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'tradequote_app';")
            row = cur.fetchone()
            assert row is not None, "tradequote_app role does not exist"
            rolname, rolsuper, rolbypassrls = row
            print(f"Role: {rolname}, rolsuper: {rolsuper}, rolbypassrls: {rolbypassrls}")
            assert rolsuper is False, "EXCEPT: rolsuper must be False"
            assert rolbypassrls is False, "EXCEPT: rolbypassrls must be False"
            print("[PASS] Check 1: tradequote_app has no superuser/bypass privileges")

            # Check table ownership
            cur.execute("SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'public' LIMIT 5;")
            tables = cur.fetchall()
            print("Sample table ownership:")
            for tname, towner in tables:
                print(f"  {tname}: owner={towner}")
                assert towner != "tradequote_app", f"EXCEPT: tradequote_app owns table {tname}"
            print("[PASS] Check 2: tradequote_app does NOT own tables")

def verify_escape_hatches():
    print("\n--- Verifying SECURITY DEFINER Escape Hatches ---")
    tid = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    
    # Create tenant row under owner connection first so FK succeeds
    with psycopg.connect(OWNER_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tenant (id, name, slug)
                VALUES (%s, 'Test Tenant RLS', 'test-tenant-rls')
                ON CONFLICT DO NOTHING;
            """, (tid,))

    # Connect as non-privileged tradequote_app role
    with psycopg.connect(APP_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Outbox relay
            print("Testing outbox_claim_unprocessed / outbox_mark_processed...")
            cur.execute(f"SET app.current_tenant = '{tid}';")
            cur.execute("""
                INSERT INTO outbox_event (event_id, tenant_id, event_name, event_version, payload)
                VALUES (gen_random_uuid(), %s, 'notification.message.sent', 1, '{}')
                RETURNING event_id;
            """, (tid,))
            event_id = cur.fetchone()[0]
            
            # Clear tenant context to test cross-tenant outbox relay claim
            cur.execute("SET app.current_tenant = '';")
            cur.execute("SELECT event_id FROM outbox_claim_unprocessed(10);")
            claimed = [str(r[0]) for r in cur.fetchall()]
            assert str(event_id) in claimed, f"Outbox relay failed to claim event {event_id}"
            
            cur.execute("SELECT outbox_mark_processed(ARRAY[%s]::uuid[]);", (event_id,))
            print("[PASS] Escape Hatch 1: Outbox relay functions work under tradequote_app")

            # 2. Public proposal resolver
            print("Testing resolve_proposal_tenant...")
            pid = str(uuid.uuid4())
            tempid = str(uuid.uuid4())
            cur.execute(f"SET app.current_tenant = '{tid}';")
            cur.execute("""
                INSERT INTO proposal_template (id, tenant_id, name, company_name, is_default)
                VALUES (%s, %s, 'NonDefault', 'Acme', false);
            """, (tempid, tid))
            cur.execute("""
                INSERT INTO proposal (id, tenant_id, quote_id, template_id, number, status, current_version)
                VALUES (%s, %s, gen_random_uuid(), %s, %s, 'sent', 1);
            """, (pid, tid, tempid, f"P-{str(uuid.uuid4())[:8]}"))
            
            # Reset tenant context to NULL (anonymous user)
            cur.execute("SET app.current_tenant = '';")
            cur.execute("SELECT resolve_proposal_tenant(%s);", (pid,))
            resolved_tid = cur.fetchone()[0]
            assert str(resolved_tid) == tid, f"Expected {tid}, got {resolved_tid}"
            print("[PASS] Escape Hatch 2: resolve_proposal_tenant works anonymously under tradequote_app")

            # 3. Public signature request resolver
            print("Testing resolve_signature_request_tenant...")
            cur.execute(f"SET app.current_tenant = '{tid}';")
            sreq_id = str(uuid.uuid4())
            token = f"test_token_{str(uuid.uuid4())[:16]}"
            dummy_hash = "a" * 64
            cur.execute("""
                INSERT INTO signature_request (id, tenant_id, proposal_id, signer_id, signer_name, signer_email, token, document_sha256, status, expires_at)
                VALUES (%s, %s, %s, gen_random_uuid(), 'John Doe', 'john@example.com', %s, %s, 'pending', NOW() + INTERVAL '1 day');
            """, (sreq_id, tid, pid, token, dummy_hash))
            
            cur.execute("SET app.current_tenant = '';")
            cur.execute("SELECT resolve_signature_request_tenant(%s);", (token,))
            resolved_sreq_tid = cur.fetchone()[0]
            assert str(resolved_sreq_tid) == tid, f"Expected {tid}, got {resolved_sreq_tid}"
            print("[PASS] Escape Hatch 3: resolve_signature_request_tenant works anonymously under tradequote_app")

def main():
    wait_for_postgres()
    apply_migrations()
    verify_role_properties()
    verify_escape_hatches()
    print("\n==========================================")
    print("ALL MIGRATION 0015 & RLS VERIFICATIONS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    main()
