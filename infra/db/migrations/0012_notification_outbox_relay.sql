-- infra/db/migrations/0012_notification_outbox_relay.sql
-- Makes the notification-service outbox relay able to see a row (T205c).
--
-- The bug this fixes, from the T205b audit: `outbox_event` is under RLS
-- (`tenant_isolation`, 0010) with `USING (tenant_id = app_current_tenant())`.
-- The relay is a cross-tenant background loop with no tenant context, and
-- `app_current_tenant()` returns NULL when the GUC is unset, so `tenant_id =
-- NULL` is never TRUE and the relay saw **zero rows, forever**. It didn't
-- crash — it logged "outbox relay started" and published nothing.
--
-- SECURITY DEFINER rather than a BYPASSRLS role: this scopes the elevated
-- privilege to exactly two operations on one table, instead of granting a
-- background loop blanket permission to read every table in the database.
-- Same pattern as resolve_proposal_tenant (0006) and
-- resolve_signature_request_tenant (0008). `SET search_path = public` is the
-- standard hardening against search-path hijacking of a definer function.

BEGIN;

-- Claim, not just fetch: FOR UPDATE SKIP LOCKED means two relay replicas take
-- disjoint batches instead of both publishing the same events. The locks are
-- held in the caller's transaction, so they release on commit.
CREATE OR REPLACE FUNCTION outbox_claim_unprocessed(p_limit integer)
RETURNS SETOF outbox_event
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT * FROM outbox_event
  WHERE processed_at IS NULL
  ORDER BY occurred_at
  LIMIT p_limit
  FOR UPDATE SKIP LOCKED;
$$;

-- Re-checks `processed_at IS NULL` so a double mark is a no-op rather than
-- overwriting the original processing timestamp. Returns the count actually
-- marked, which lets the caller notice a claim it didn't win.
CREATE OR REPLACE FUNCTION outbox_mark_processed(p_event_ids uuid[])
RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  WITH updated AS (
    UPDATE outbox_event
       SET processed_at = now()
     WHERE event_id = ANY(p_event_ids)
       AND processed_at IS NULL
    RETURNING 1
  )
  SELECT count(*)::integer FROM updated;
$$;

INSERT INTO schema_migrations(version) VALUES ('0012') ON CONFLICT (version) DO NOTHING;

COMMIT;
