-- infra/db/migrations/0011_notification_idempotency.sql
-- Request-level idempotency for notification sends (T205b).
--
-- Without this, a client that retries POST /v1/notifications/send after a
-- timeout creates a second ledger row and sends the message twice. The partial
-- unique index is what actually closes the race: the route's check-then-insert
-- lookup alone would let two concurrent identical requests both miss and both
-- insert. Scoped to (tenant_id, idempotency_key) so keys are per-tenant and one
-- tenant can never collide with — or probe for — another's key.
--
-- Authored by Agent 4 under services/notification-service/; relocated here by
-- Agent 1 during the T205b audit, since infra/db/migrations/ is the only path
-- the schema is applied from (docs/06-DATABASE-SCHEMA.md) and is Agent 1-owned.

BEGIN;

ALTER TABLE notification_message
  ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_message_idempotency
  ON notification_message(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

INSERT INTO schema_migrations(version) VALUES ('0011') ON CONFLICT (version) DO NOTHING;

COMMIT;
