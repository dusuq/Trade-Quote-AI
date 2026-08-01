-- infra/db/migrations/0007_analytics.sql
-- 0007 — Analytics Service (Module M21). Owns: analytics_events table + RLS tenant isolation.

BEGIN;

CREATE TABLE IF NOT EXISTS analytics_events (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  quote_id       uuid NOT NULL,
  customer_id    uuid NOT NULL,
  customer_name  text NOT NULL,
  event_type     text NOT NULL,
  trade          text NOT NULL,
  amount_minor   bigint NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_tenant_quote_event UNIQUE (tenant_id, quote_id, event_type)
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_tenant ON analytics_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_quote ON analytics_events(quote_id);

-- RLS policy following conventions §2 (mirrors 0005_quote.sql / 0006_proposal.sql)
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON analytics_events;
CREATE POLICY tenant_isolation ON analytics_events
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

INSERT INTO schema_migrations(version) VALUES ('0007') ON CONFLICT (version) DO NOTHING;

COMMIT;
