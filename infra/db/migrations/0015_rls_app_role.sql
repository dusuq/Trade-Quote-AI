-- infra/db/migrations/0015_rls_app_role.sql
-- T310 (M27 security review): make Row-Level Security actually apply to the
-- application.
--
-- THE BUG
-- -------
-- Every tenant-scoped table has `ENABLE ROW LEVEL SECURITY` with a
-- `tenant_isolation` policy. But `ENABLE` does not apply to the table's
-- OWNER — only `FORCE` does. Migrations run as the role in DATABASE_URL, so
-- that role owns every table; and the services' default DATABASE_URL is the
-- *same* role (`tradequote`). No separate application role is created anywhere
-- in infra/.
--
-- Net effect: in the default configuration the application connects as the
-- table owner, so **every tenant_isolation policy is bypassed** and RLS
-- provides no isolation at all. The only thing keeping tenants apart is that
-- service queries also filter on tenant_id by hand — defence in depth with
-- nothing behind it. One forgotten WHERE clause is a cross-tenant data breach.
--
-- This was not caught because tests/integration/test_postgres_rls.py
-- `skipif`s itself when Postgres is unreachable, which is the normal local
-- state — so the suite reported green without ever evaluating a policy.
--
-- THE FIX
-- -------
-- Create a dedicated, least-privilege, NON-OWNER role for the services to
-- connect as. RLS applies to it normally, so the existing policies start
-- doing their job with no policy changes at all.
--
-- WHY NOT `FORCE ROW LEVEL SECURITY` EVERYWHERE
-- ---------------------------------------------
-- Considered and deliberately rejected. Three SECURITY DEFINER functions
-- depend on the owner exemption as their intended, tightly-scoped escape
-- hatch:
--
--   * outbox_claim_unprocessed / outbox_mark_processed (0012) — the
--     notification relay is a cross-tenant background loop with no tenant
--     context. FORCE would make `tenant_id = app_current_tenant()` (NULL)
--     match zero rows and the relay would silently publish nothing forever:
--     precisely the T205c bug, reintroduced.
--   * resolve_proposal_tenant (0006) and resolve_signature_request_tenant
--     (0008) — these back the PUBLIC, unauthenticated proposal-view and
--     e-signature links, which have no tenant context by definition. FORCE
--     would break customer signing links.
--
-- Adding FORCE would therefore trade a fixable misconfiguration for three
-- silent functional outages. The owner exemption is load-bearing; the correct
-- fix is to stop *being* the owner in application code paths, which is what
-- this migration does.
--
-- VERIFY AFTER APPLYING (must be run against a live database — see
-- docs/13-SECURITY-REVIEW-OWASP.md):
--   SELECT rolname, rolsuper, rolbypassrls FROM pg_roles
--    WHERE rolname = 'tradequote_app';
--   -- expect: rolsuper = f, rolbypassrls = f

BEGIN;

-- ── 1. The application role ──────────────────────────────────────────────────
-- NOLOGIN + no password on purpose: the credential is environment-specific and
-- must never be committed. Grant login per environment, e.g.
--   ALTER ROLE tradequote_app WITH LOGIN PASSWORD '<from secret manager>';
-- or, on GCP Cloud SQL, prefer IAM database authentication and skip passwords
-- entirely (see the T310 GCP handoff).
--
-- NOSUPERUSER and NOBYPASSRLS are stated explicitly rather than relied on as
-- defaults: both would silently defeat every policy this migration exists to
-- enforce.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradequote_app') THEN
    CREATE ROLE tradequote_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  ELSE
    -- Idempotent re-assert: if someone widened these by hand, put them back.
    ALTER ROLE tradequote_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

-- ── 2. Least-privilege grants ────────────────────────────────────────────────
-- Connect + read the schema, but no DDL: the application must never be able to
-- ALTER a table, and specifically must never be able to DROP a policy.
-- GRANT ... ON DATABASE takes a literal name, not an expression, so the
-- current database has to be interpolated via dynamic SQL.
DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO tradequote_app', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO tradequote_app;

-- DML on existing tables. No TRUNCATE (it bypasses row-level DELETE policies),
-- and no ownership.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO tradequote_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tradequote_app;

-- The SECURITY DEFINER escape hatches the services legitimately call.
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO tradequote_app;

-- Tables created by future migrations inherit the same grants automatically,
-- so a new table can't accidentally be unreachable (or over-granted) later.
-- FOR ROLE is the migration/owner role, since that is what creates objects.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tradequote_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO tradequote_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO tradequote_app;

-- ── 3. Explicitly deny the dangerous shapes ──────────────────────────────────
-- PUBLIC keeps CREATE on the public schema in PostgreSQL < 15; revoking it
-- stops any role from adding objects that sidestep these grants.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

INSERT INTO schema_migrations(version) VALUES ('0015') ON CONFLICT (version) DO NOTHING;

COMMIT;
