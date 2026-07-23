-- 0004 — Pricebook (Module M6). Owns: catalog items + regional pricing.

BEGIN;

DO $$ BEGIN
  CREATE TYPE item_kind AS ENUM ('material','labor','equipment','consumable','rental','package');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS pricebook_item (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  kind           item_kind NOT NULL,
  sku            text,
  name           text NOT NULL,
  description    text,
  unit           text NOT NULL DEFAULT 'each',       -- each | hour | ft | m | box ...
  unit_cost_minor bigint NOT NULL DEFAULT 0,          -- cost in minor units (cents)
  default_markup_bps int NOT NULL DEFAULT 0,          -- basis points (10000 = 100%)
  currency       text NOT NULL DEFAULT 'USD',
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, sku)
);
DROP TRIGGER IF EXISTS trg_pricebook_item_touch ON pricebook_item;
CREATE TRIGGER trg_pricebook_item_touch BEFORE UPDATE ON pricebook_item
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_pricebook_name_trgm ON pricebook_item USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_pricebook_kind ON pricebook_item(tenant_id, kind);

-- Regional overrides (e.g. different labor rate per state/metro).
CREATE TABLE IF NOT EXISTS pricebook_region_price (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  item_id        uuid NOT NULL REFERENCES pricebook_item(id) ON DELETE CASCADE,
  region_code    text NOT NULL,                       -- e.g. 'US-CA', 'AU-NSW'
  unit_cost_minor bigint NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (item_id, region_code)
);

-- RLS
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pricebook_item','pricebook_region_price'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

INSERT INTO schema_migrations(version) VALUES ('0004') ON CONFLICT (version) DO NOTHING;

COMMIT;
