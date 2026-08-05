-- 0016 — Security observability: the privileged-action audit log (T310b / M27).
-- Idempotent. Safe to re-run. Conventions: docs/06-DATABASE-SCHEMA.md
--
-- WHY
-- ---
-- The T310 OWASP review flagged **A09 (Logging & Monitoring Failures)**: the
-- platform had availability alerting (T309) and request metrics (T309b) but no
-- application-level *security* record. `auth_audit_log` has existed since 0002
-- and nothing has ever written a row to it — a table that exists but is never
-- written is worse than no table, because it reads on the schema diagram as a
-- control that is in place.
--
-- T310b starts writing it (services/auth-service/app/application/audit.py) and
-- this migration makes it fit for the job:
--
--   1. It records more than auth. `outcome`, `target_type`/`target_id` and
--      `request_id` turn an auth-only log into a general privileged-action log
--      — "who did what to which object, and did it work" — so a role grant, a
--      user suspension, or a tenant setting change lands in the same place as
--      a login. `action` stays free-text on purpose: a CHECK constraint here
--      would mean a schema migration every time a service records a new kind
--      of privileged action, and the pressure to skip that is exactly how
--      audit logging quietly stops happening.
--
--   2. `actor_email` records WHO was attempted, not just who succeeded. A
--      failed login has no `actor_id` — that is the whole point, the user did
--      not authenticate — so without this column a credential-stuffing run
--      writes a pile of rows with a NULL actor and no way to tell whether it
--      hit one account 10,000 times or 10,000 accounts once. That distinction
--      is the entire investigation.
--
--      ⚠️ This column holds ATTACKER-CONTROLLED text on failed attempts (the
--      email submitted, which need not correspond to any real user). It is
--      length-capped by the writer and must be escaped by any UI that renders
--      it. Treat it as untrusted input, not as a verified identity.
--
--   3. It becomes append-only for the application role. An audit log the
--      application can UPDATE or DELETE is a log an attacker who reaches the
--      application can edit — which is precisely the scenario it exists to
--      reconstruct. The migration/owner role retains full rights so retention
--      pruning is still possible as a deliberate, privileged operation.

BEGIN;

-- ── 1. Widen the record ──────────────────────────────────────────────────────
ALTER TABLE auth_audit_log ADD COLUMN IF NOT EXISTS outcome     text NOT NULL DEFAULT 'success';
ALTER TABLE auth_audit_log ADD COLUMN IF NOT EXISTS actor_email text;
ALTER TABLE auth_audit_log ADD COLUMN IF NOT EXISTS target_type text;
ALTER TABLE auth_audit_log ADD COLUMN IF NOT EXISTS target_id   uuid;
ALTER TABLE auth_audit_log ADD COLUMN IF NOT EXISTS request_id  text;

-- Two values only. Unlike `action`, this one IS closed: every alert and every
-- query in the runbook splits on success vs failure, and a third spelling
-- ('failed', 'error') would silently drop rows out of the failure rate.
DO $$ BEGIN
  ALTER TABLE auth_audit_log
    ADD CONSTRAINT auth_audit_log_outcome_chk CHECK (outcome IN ('success', 'failure'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 2. Indexes for the questions actually asked during an incident ───────────
-- "show me every failed login for this tenant in the last hour" — partial, so
-- it stays small even though failures are the rare case.
CREATE INDEX IF NOT EXISTS idx_auth_audit_failures
  ON auth_audit_log(tenant_id, created_at DESC) WHERE outcome = 'failure';
-- "show me every role change for this tenant".
CREATE INDEX IF NOT EXISTS idx_auth_audit_action
  ON auth_audit_log(tenant_id, action, created_at DESC);
-- "was this account the target of the burst" — the credential-stuffing shape.
CREATE INDEX IF NOT EXISTS idx_auth_audit_actor_email
  ON auth_audit_log(tenant_id, actor_email, created_at DESC) WHERE actor_email IS NOT NULL;

-- ── 3. Append-only for the application role ──────────────────────────────────
-- 0015 granted SELECT/INSERT/UPDATE/DELETE on ALL TABLES to tradequote_app;
-- this narrows that back down for this one table. Ordering matters and is
-- guaranteed by the file numbering — 0016 runs after 0015.
--
-- TRUNCATE is revoked explicitly even though 0015 never granted it: TRUNCATE
-- bypasses row-level DELETE policies entirely, so it is the one statement that
-- could empty this table without RLS having any say.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradequote_app') THEN
    EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON auth_audit_log FROM tradequote_app';
  END IF;
END $$;

-- Future tables must not silently inherit write-everything either — but that
-- is 0015's ALTER DEFAULT PRIVILEGES, which is correct for ordinary tables.
-- Any future audit-style table must repeat the REVOKE above; there is no way
-- to express "append-only by default" in ALTER DEFAULT PRIVILEGES.

INSERT INTO schema_migrations(version) VALUES ('0016') ON CONFLICT (version) DO NOTHING;

COMMIT;
