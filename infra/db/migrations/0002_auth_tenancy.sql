-- 0002 — Auth & tenancy (Module M1). Owns: tenants, users, RBAC, MFA, sessions, audit.

BEGIN;

-- ── Enums ────────────────────────────────────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE plan_tier AS ENUM ('starter', 'professional', 'business', 'enterprise');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE user_status AS ENUM ('invited', 'active', 'suspended', 'disabled');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── tenant (the tenancy root — NOT tenant-scoped itself) ─────────────────────
CREATE TABLE IF NOT EXISTS tenant (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL,
  slug         citext UNIQUE NOT NULL,
  plan         plan_tier NOT NULL DEFAULT 'starter',
  country      text NOT NULL DEFAULT 'US',
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_tenant_touch ON tenant;
CREATE TRIGGER trg_tenant_touch BEFORE UPDATE ON tenant
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── role & permission (RBAC) ─────────────────────────────────────────────────
-- Roles are per-tenant so a tenant can customize; system roles are seeded.
CREATE TABLE IF NOT EXISTS role (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  key          text NOT NULL,   -- owner|admin|estimator|technician|salesperson|office|accountant|viewer
  name         text NOT NULL,
  is_system    boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, key)
);

CREATE TABLE IF NOT EXISTS permission (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key          text UNIQUE NOT NULL,  -- e.g. 'quote.write', 'pricebook.read' (global catalog)
  description  text
);

CREATE TABLE IF NOT EXISTS role_permission (
  role_id       uuid NOT NULL REFERENCES role(id) ON DELETE CASCADE,
  permission_id uuid NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);

-- ── app_user ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_user (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  email          citext NOT NULL,
  full_name      text,
  password_hash  text,                 -- null when SSO-only (Clerk/Auth0/OAuth)
  external_idp   text,                 -- 'clerk' | 'auth0' | 'google' | 'microsoft' | null
  status         user_status NOT NULL DEFAULT 'invited',
  last_login_at  timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);
DROP TRIGGER IF EXISTS trg_app_user_touch ON app_user;
CREATE TRIGGER trg_app_user_touch BEFORE UPDATE ON app_user
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS user_role (
  tenant_id   uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  role_id     uuid NOT NULL REFERENCES role(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);

-- ── MFA (TOTP) ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mfa_secret (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  user_id       uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  secret_enc    text NOT NULL,         -- encrypted TOTP secret (never plaintext)
  confirmed_at  timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id)
);

-- ── refresh tokens (rotating) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS refresh_token (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  user_id       uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  token_hash    text NOT NULL,         -- store only the hash
  expires_at    timestamptz NOT NULL,
  revoked_at    timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refresh_token_user ON refresh_token(user_id);

-- ── auth audit log ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auth_audit_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_id      uuid REFERENCES app_user(id) ON DELETE SET NULL,
  action        text NOT NULL,         -- 'login' | 'login_failed' | 'mfa_verified' | 'user_invited' ...
  ip_address    inet,
  user_agent    text,
  metadata      jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_audit_tenant_time ON auth_audit_log(tenant_id, created_at DESC);

-- ── Row-Level Security (tenant isolation) ────────────────────────────────────
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'role','app_user','user_role','mfa_secret','refresh_token','auth_audit_log'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

INSERT INTO schema_migrations(version) VALUES ('0002') ON CONFLICT (version) DO NOTHING;

COMMIT;
