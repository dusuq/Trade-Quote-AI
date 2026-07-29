-- infra/db/migrations/0009_ai_service.sql
-- 0009 — AI Quote Assistant (Module M15 / T201). Owns: ai_usage_log.
--
-- The service creates quotes and reads the pricebook over HTTP (ADR-0003),
-- so it owns no quote or pricebook tables — only its own usage ledger.

BEGIN;

-- Append-only metering ledger: one row per billed AI call.
--
-- `feature`, `model_id`, and `input_kind` are deliberately `text` rather than
-- Postgres enums. This table must keep accepting rows when a new model id or
-- feature ships, and requiring a schema migration before a usage record can
-- be written is a poor gate on billing telemetry. It also sidesteps the
-- `values_callable` enum trap from T206b entirely.
CREATE TABLE IF NOT EXISTS ai_usage_log (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  feature      text NOT NULL,          -- 'voice' | 'scope_writer' | future features
  model_id     text NOT NULL,          -- e.g. 'claude-opus-5', 'whisper-1'
  input_kind   text NOT NULL,          -- 'voice' | 'text' | 'image'
  tokens_used  integer NOT NULL DEFAULT 0,
  -- Money in minor units (conventions §5). bigint because a busy tenant's
  -- lifetime spend in cents should never be the thing that overflows.
  cost_minor   bigint NOT NULL DEFAULT 0,
  metadata     jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_log_tenant ON ai_usage_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_feature ON ai_usage_log(tenant_id, feature);
-- Serves both the /usage listing (newest first) and the daily spend cap,
-- which sums cost_minor over a tenant's rows since midnight UTC.
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_created ON ai_usage_log(tenant_id, created_at DESC);

-- RLS (conventions §2) — mirrors 0006_proposal.sql / 0008_esign.sql exactly.
ALTER TABLE ai_usage_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON ai_usage_log;
CREATE POLICY tenant_isolation ON ai_usage_log
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

INSERT INTO schema_migrations(version) VALUES ('0009') ON CONFLICT (version) DO NOTHING;

COMMIT;
