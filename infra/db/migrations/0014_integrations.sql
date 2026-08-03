-- 0014 — Integrations (Module M23). Owns: integration_connection, webhook_subscription, sync_log.

BEGIN;

CREATE TABLE IF NOT EXISTS integration_connection (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  provider                text NOT NULL, -- quickbooks | xero | zapier
  status                  text NOT NULL DEFAULT 'pending', -- pending | active | expired | revoked | error
  external_account_id     text,
  display_name            text,
  access_token_encrypted  text,
  refresh_token_encrypted text,
  token_expires_at        timestamptz,
  scopes                  text,
  config_json             jsonb,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  created_by              uuid REFERENCES app_user(id) ON DELETE SET NULL
);

DROP TRIGGER IF EXISTS trg_integration_connection_touch ON integration_connection;
CREATE TRIGGER trg_integration_connection_touch BEFORE UPDATE ON integration_connection
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_integration_conn_tenant_provider ON integration_connection(tenant_id, provider);

CREATE TABLE IF NOT EXISTS webhook_subscription (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  connection_id  uuid NOT NULL REFERENCES integration_connection(id) ON DELETE CASCADE,
  target_url     text NOT NULL,
  event_types    jsonb NOT NULL DEFAULT '[]'::jsonb,
  secret         text,
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhook_sub_connection ON webhook_subscription(connection_id);

CREATE TABLE IF NOT EXISTS sync_log (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  connection_id    uuid NOT NULL REFERENCES integration_connection(id) ON DELETE CASCADE,
  direction        text NOT NULL, -- push | pull
  entity_type      text NOT NULL, -- invoice | customer | quote
  entity_id        uuid,
  status           text NOT NULL DEFAULT 'pending', -- pending | running | success | failed
  external_id      text,
  error_message    text,
  request_payload  jsonb,
  response_payload jsonb,
  started_at       timestamptz NOT NULL DEFAULT now(),
  completed_at     timestamptz
);

CREATE INDEX IF NOT EXISTS idx_sync_log_connection ON sync_log(connection_id, started_at DESC);

-- RLS
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['integration_connection','webhook_subscription','sync_log'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

INSERT INTO schema_migrations(version) VALUES ('0014') ON CONFLICT (version) DO NOTHING;

COMMIT;
