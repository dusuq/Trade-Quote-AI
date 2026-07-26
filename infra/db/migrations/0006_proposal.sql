-- infra/db/migrations/0006_proposal.sql
-- 0006 — Proposal Builder (Module M8). Owns: proposal_template, proposal, proposal_version.
-- Extends T107's stateless PDF engine (services/proposal-service) with persistence.

BEGIN;

DO $$ BEGIN
  CREATE TYPE proposal_status AS ENUM ('draft', 'sent', 'viewed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS proposal_template (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  name                   text NOT NULL,
  company_name           text NOT NULL,
  logo_url               text,
  primary_color          text NOT NULL DEFAULT '#111827',
  phone                  text,
  email                  text,
  website                text,
  default_terms_text     text,
  default_warranty_text  text,
  is_default             boolean NOT NULL DEFAULT false,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_proposal_template_touch ON proposal_template;
CREATE TRIGGER trg_proposal_template_touch BEFORE UPDATE ON proposal_template
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
-- Only one default template per tenant, enforced at the DB level (spec §7).
CREATE UNIQUE INDEX IF NOT EXISTS proposal_template_one_default_per_tenant
  ON proposal_template (tenant_id) WHERE is_default;

CREATE TABLE IF NOT EXISTS proposal (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  quote_id          uuid NOT NULL,   -- logical reference only (spec D5); quote lives in quote-service
  template_id       uuid NOT NULL REFERENCES proposal_template(id),
  number            text NOT NULL,   -- "P-2026-000001", same scheme as quote.number
  status            proposal_status NOT NULL DEFAULT 'draft',
  current_version   int NOT NULL DEFAULT 1,
  storage_key       text,
  sent_at           timestamptz,
  viewed_at         timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, number)
);
DROP TRIGGER IF EXISTS trg_proposal_touch ON proposal;
CREATE TRIGGER trg_proposal_touch BEFORE UPDATE ON proposal
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_proposal_quote ON proposal(quote_id);
CREATE INDEX IF NOT EXISTS idx_proposal_status ON proposal(tenant_id, status);

CREATE TABLE IF NOT EXISTS proposal_version (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  proposal_id   uuid NOT NULL REFERENCES proposal(id) ON DELETE CASCADE,
  version       int NOT NULL,
  snapshot      jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (proposal_id, version)
);

-- RLS (conventions §2) — mirrors 0005_quote.sql's pattern exactly.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['proposal_template','proposal','proposal_version'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

-- Resolves which tenant owns a proposal, bypassing RLS for this one narrow
-- lookup. Needed because GET /v1/proposals/{id}/view has no tenant context
-- at all — there is no session, no header, nothing to set app.current_tenant
-- from. SECURITY DEFINER makes this function run with its owner's
-- privileges (the migration-owner role, which is the proposal table's
-- owner and therefore already bypasses RLS on it) regardless of who calls
-- it. `SET search_path = public` is a standard hardening step for
-- SECURITY DEFINER functions, preventing search-path hijacking.
CREATE OR REPLACE FUNCTION resolve_proposal_tenant(p_proposal_id uuid) RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT tenant_id FROM proposal WHERE id = p_proposal_id;
$$;

INSERT INTO schema_migrations(version) VALUES ('0006') ON CONFLICT (version) DO NOTHING;

COMMIT;
