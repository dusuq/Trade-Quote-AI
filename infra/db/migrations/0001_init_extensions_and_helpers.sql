-- 0001 — Extensions + multi-tenant helpers
-- Idempotent. Safe to run standalone (psql) or via the docker init hook.
-- TradeQuote AI schema v1 (T102). Conventions: docs/06-DATABASE-SCHEMA.md

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ── Multi-tenancy contract ───────────────────────────────────────────────────
-- Every tenant-scoped table carries tenant_id and is protected by RLS. The app
-- sets the active tenant per transaction:  SET LOCAL app.current_tenant = '<uuid>';
-- Reads/writes then transparently filter to that tenant. Never cross tenants.

-- Returns the current tenant from the session GUC, or NULL if unset.
CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_tenant', true), '')::uuid;
$$;

-- updated_at auto-touch trigger function (attached per table below).
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- Migration ledger so a runner can tell what has been applied.
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     text PRIMARY KEY,
  applied_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations(version) VALUES ('0001')
ON CONFLICT (version) DO NOTHING;

COMMIT;
