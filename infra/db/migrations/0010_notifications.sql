-- infra/db/migrations/0010_notifications.sql
-- 0010 — Notifications (Module M22 / T205). Owns: notification_template,
-- notification_message, and this service's transactional outbox_event table.
-- Consumes quote/proposal/esign ids by logical reference only (no cross-context
-- FK — same rule as proposal.quote_id in 0006 and signature_request.proposal_id
-- in 0008).

BEGIN;

-- Custom templates defined by tenants (fall back to built-in defaults in code).
CREATE TABLE IF NOT EXISTS notification_template (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  name             text NOT NULL,          -- 'quote_delivery' | 'proposal_delivery' | 'signature_request'
  channel          text NOT NULL,          -- 'email' | 'sms' | 'whatsapp' | 'push'
  subject_template text,                   -- email subject (null for SMS)
  body_template    text NOT NULL,          -- Jinja2 message body
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_tenant_template_channel UNIQUE (tenant_id, name, channel)
);
DROP TRIGGER IF EXISTS trg_notification_template_touch ON notification_template;
CREATE TRIGGER trg_notification_template_touch BEFORE UPDATE ON notification_template
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Core delivery ledger.
CREATE TABLE IF NOT EXISTS notification_message (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  channel             text NOT NULL,       -- 'email' | 'sms' | 'whatsapp' | 'push'
  recipient           text NOT NULL,       -- plain-text phone or email; RLS-protected, never logged
  to_redacted         text NOT NULL,       -- redacted form used in events/logs
  template_name       text NOT NULL,       -- which template produced this message
  subject             text,                -- rendered email subject (null for SMS)
  body                text NOT NULL,       -- rendered message body
  status              text NOT NULL DEFAULT 'queued', -- 'queued' | 'sending' | 'sent' | 'failed'
  provider            text,                -- 'console' | 'sendgrid' | 'resend' | 'twilio'
  provider_message_id text,                -- reference id from the provider
  error_message       text,                -- populated when status = 'failed'
  reference_kind      text,                -- 'quote' | 'proposal' | 'esign'
  reference_id        uuid,                -- id of the associated document
  created_at          timestamptz NOT NULL DEFAULT now(),
  sent_at             timestamptz,
  updated_at          timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_notification_message_touch ON notification_message;
CREATE TRIGGER trg_notification_message_touch BEFORE UPDATE ON notification_message
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_notification_template_lookup ON notification_template(tenant_id, name);
CREATE INDEX IF NOT EXISTS idx_notification_message_tenant ON notification_message(tenant_id);
CREATE INDEX IF NOT EXISTS idx_notification_message_status ON notification_message(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_notification_message_ref ON notification_message(tenant_id, reference_kind, reference_id);
CREATE INDEX IF NOT EXISTS idx_notification_message_created ON notification_message(tenant_id, created_at DESC);

-- Transactional outbox for domain events (conventions §4). notification-service
-- is the first service to actually persist to an outbox table; earlier services
-- carry a TODO(outbox) and rely on the returned event. The relay/consumer is a
-- future capability — this table is the durable, tenant-scoped source for it.
CREATE TABLE IF NOT EXISTS outbox_event (
  event_id        uuid PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  event_name      text NOT NULL,
  event_version   integer NOT NULL DEFAULT 1,
  payload         jsonb NOT NULL,
  actor_id        uuid,
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  correlation_id  uuid,
  causation_id    uuid,
  processed_at    timestamptz
);
CREATE INDEX IF NOT EXISTS idx_outbox_event_unprocessed
  ON outbox_event(tenant_id, occurred_at) WHERE processed_at IS NULL;

-- RLS (conventions §2) — mirrors 0008_esign.sql's loop.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['notification_template','notification_message','outbox_event'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

INSERT INTO schema_migrations(version) VALUES ('0010') ON CONFLICT (version) DO NOTHING;

COMMIT;
