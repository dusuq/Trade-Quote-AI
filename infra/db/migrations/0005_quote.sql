-- 0005 — Quote/Estimate (Module M7). Owns: quotes, versions, line items.
-- Money is always integer minor units (cents). Margin/markup in basis points.

BEGIN;

DO $$ BEGIN
  CREATE TYPE quote_status AS ENUM
    ('draft','sent','viewed','accepted','rejected','expired','archived');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE quote_created_via AS ENUM ('manual','voice','vision','ocr');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS quote (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  customer_id      uuid NOT NULL REFERENCES customer(id) ON DELETE RESTRICT,
  property_id      uuid REFERENCES property(id) ON DELETE SET NULL,
  number           text NOT NULL,                     -- human ref e.g. Q-2026-000123
  title            text,
  status           quote_status NOT NULL DEFAULT 'draft',
  created_via      quote_created_via NOT NULL DEFAULT 'manual',
  currency         text NOT NULL DEFAULT 'USD',
  tax_rate_bps     int NOT NULL DEFAULT 0,             -- 875 = 8.75%
  subtotal_minor   bigint NOT NULL DEFAULT 0,
  tax_minor        bigint NOT NULL DEFAULT 0,
  total_minor      bigint NOT NULL DEFAULT 0,
  current_version  int NOT NULL DEFAULT 1,
  valid_until      date,
  owner_id         uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, number)
);
DROP TRIGGER IF EXISTS trg_quote_touch ON quote;
CREATE TRIGGER trg_quote_touch BEFORE UPDATE ON quote
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_quote_customer ON quote(customer_id);
CREATE INDEX IF NOT EXISTS idx_quote_status ON quote(tenant_id, status);

-- Immutable snapshots for versioning / audit (each send creates a version).
CREATE TABLE IF NOT EXISTS quote_version (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  quote_id         uuid NOT NULL REFERENCES quote(id) ON DELETE CASCADE,
  version          int NOT NULL,
  snapshot         jsonb NOT NULL,                     -- full quote + line items at send time
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (quote_id, version)
);

CREATE TABLE IF NOT EXISTS quote_line_item (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  quote_id         uuid NOT NULL REFERENCES quote(id) ON DELETE CASCADE,
  pricebook_item_id uuid REFERENCES pricebook_item(id) ON DELETE SET NULL,
  kind             item_kind NOT NULL DEFAULT 'material',
  description      text NOT NULL,
  quantity         numeric(14,3) NOT NULL DEFAULT 1,
  unit             text NOT NULL DEFAULT 'each',
  unit_cost_minor  bigint NOT NULL DEFAULT 0,          -- cost basis
  markup_bps       int NOT NULL DEFAULT 0,             -- margin/markup in basis points
  unit_price_minor bigint NOT NULL DEFAULT 0,          -- price shown to customer
  line_total_minor bigint NOT NULL DEFAULT 0,          -- quantity * unit_price
  is_optional      boolean NOT NULL DEFAULT false,
  sort_order       int NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_line_item_quote ON quote_line_item(quote_id, sort_order);

-- RLS
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['quote','quote_version','quote_line_item'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

INSERT INTO schema_migrations(version) VALUES ('0005') ON CONFLICT (version) DO NOTHING;

COMMIT;
