-- infra/db/migrations/0008_esign.sql
-- 0008 — E-Signature (Module M10 / T204). Owns: signature_request, signature,
-- signature_audit_event. Consumes proposal ids from proposal-service by
-- logical reference only (no cross-context FK — same rule as proposal.quote_id).
--
-- Numbering note: 0007 is reserved for T307b (analytics), already communicated
-- to Agent 3 in docs/handoffs/T307b-T311-antigravity-handoff.md.

BEGIN;

DO $$ BEGIN
  CREATE TYPE signature_request_status AS ENUM
    ('pending', 'signed', 'declined', 'voided', 'expired');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE signature_method AS ENUM ('typed', 'drawn');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS signature_request (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  proposal_id      uuid NOT NULL,   -- logical reference; proposal lives in proposal-service
  signer_id        uuid NOT NULL,   -- synthetic identity for an external signer with no account
  signer_name      text NOT NULL,
  signer_email     text NOT NULL,
  -- The capability for the public signing link: secrets.token_urlsafe(32).
  -- Deliberately not the row id — see design spec D2.
  token            text NOT NULL UNIQUE,
  document_sha256  char(64) NOT NULL,
  status           signature_request_status NOT NULL DEFAULT 'pending',
  expires_at       timestamptz NOT NULL,
  signed_at        timestamptz,
  declined_at      timestamptz,
  voided_at        timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_signature_request_touch ON signature_request;
CREATE TRIGGER trg_signature_request_touch BEFORE UPDATE ON signature_request
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_signature_request_proposal ON signature_request(proposal_id);
CREATE INDEX IF NOT EXISTS idx_signature_request_status ON signature_request(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_signature_request_token ON signature_request(token);

-- Evidence tables below intentionally do NOT cascade from signature_request:
-- deleting a signing request must not silently destroy the signature or the
-- audit chain that proves it happened. A deliberate purge has to remove the
-- evidence first, as an explicit act.
CREATE TABLE IF NOT EXISTS signature (
  id                                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                         uuid NOT NULL REFERENCES tenant(id),
  request_id                        uuid NOT NULL UNIQUE REFERENCES signature_request(id),
  signer_id                         uuid NOT NULL,
  signer_name                       text NOT NULL,
  signer_email                      text NOT NULL,
  method                            signature_method NOT NULL,
  typed_name                        text,
  image_data                        text,
  signature_hash                    char(64) NOT NULL,
  document_sha256                   char(64) NOT NULL,
  ip_address                        text NOT NULL,
  user_agent                        text,
  consented_to_electronic_business  boolean NOT NULL,
  intent_affirmed                   boolean NOT NULL,
  signed_at                         timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signature_request ON signature(request_id);

CREATE TABLE IF NOT EXISTS signature_audit_event (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id),
  request_id   uuid NOT NULL REFERENCES signature_request(id),
  sequence     int NOT NULL,
  event_type   text NOT NULL,
  payload      jsonb NOT NULL,
  occurred_at  timestamptz NOT NULL,
  prev_hash    char(64) NOT NULL,
  entry_hash   char(64) NOT NULL,
  UNIQUE (request_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_signature_audit_request ON signature_audit_event(request_id, sequence);

-- Append-only enforcement.
--
-- The hash chain proves a chain is *self-consistent*; it cannot stop someone
-- with full write access from rewriting an entry and recomputing the tail
-- (documented honestly in the M10 spec and asserted by
-- test_full_rechain_passes_documenting_the_limit_of_a_self_contained_chain).
-- This trigger is the operational control that closes that gap at the
-- database: audit rows can be inserted, never modified or removed.
--
-- A legitimate purge (GDPR erasure, tenant offboarding) must therefore drop
-- this trigger inside an explicit maintenance transaction — which is the
-- intended friction. Destroying signature evidence should be a deliberate,
-- reviewable act, not a side effect of an ORM call.
CREATE OR REPLACE FUNCTION signature_audit_event_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'signature_audit_event is append-only; % is not permitted', TG_OP;
END $$;

DROP TRIGGER IF EXISTS trg_signature_audit_event_append_only ON signature_audit_event;
CREATE TRIGGER trg_signature_audit_event_append_only
  BEFORE UPDATE OR DELETE ON signature_audit_event
  FOR EACH ROW EXECUTE FUNCTION signature_audit_event_append_only();

-- RLS (conventions §2) — mirrors 0006_proposal.sql's pattern exactly.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['signature_request','signature','signature_audit_event'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

-- Resolves which tenant owns a signing token, bypassing RLS for this one
-- narrow lookup. `/v1/sign/{token}` arrives with no tenant context at all —
-- no session, no header — so a normal query would run with no
-- app.current_tenant set and see zero rows.
--
-- Returns ONLY tenant_id: same minimal-surface reasoning as
-- resolve_proposal_tenant in 0006. `SET search_path = public` is the standard
-- hardening against search-path hijacking of a SECURITY DEFINER function.
CREATE OR REPLACE FUNCTION resolve_signature_request_tenant(p_token text) RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT tenant_id FROM signature_request WHERE token = p_token;
$$;

INSERT INTO schema_migrations(version) VALUES ('0008') ON CONFLICT (version) DO NOTHING;

COMMIT;
