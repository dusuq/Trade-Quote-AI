-- 0003 — Customer CRM (Module M4). Owns: customers, contacts, properties, tags, notes.

BEGIN;

CREATE TABLE IF NOT EXISTS customer (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  display_name   text NOT NULL,
  company_name   text,
  email          citext,
  phone          text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_customer_touch ON customer;
CREATE TRIGGER trg_customer_touch BEFORE UPDATE ON customer
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_customer_name_trgm ON customer USING gin (display_name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS contact (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  customer_id    uuid NOT NULL REFERENCES customer(id) ON DELETE CASCADE,
  name           text NOT NULL,
  email          citext,
  phone          text,
  is_primary     boolean NOT NULL DEFAULT false,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contact_customer ON contact(customer_id);

CREATE TABLE IF NOT EXISTS property (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  customer_id    uuid NOT NULL REFERENCES customer(id) ON DELETE CASCADE,
  address_line1  text NOT NULL,
  address_line2  text,
  city           text,
  region         text,        -- state/province
  postal_code    text,
  country        text NOT NULL DEFAULT 'US',
  lat            double precision,
  lng            double precision,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_property_customer ON property(customer_id);

CREATE TABLE IF NOT EXISTS tag (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  label          text NOT NULL,
  color          text,
  UNIQUE (tenant_id, label)
);

CREATE TABLE IF NOT EXISTS customer_tag (
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  customer_id    uuid NOT NULL REFERENCES customer(id) ON DELETE CASCADE,
  tag_id         uuid NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY (customer_id, tag_id)
);

CREATE TABLE IF NOT EXISTS customer_note (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  customer_id    uuid NOT NULL REFERENCES customer(id) ON DELETE CASCADE,
  author_id      uuid REFERENCES app_user(id) ON DELETE SET NULL,
  body           text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_note_customer ON customer_note(customer_id, created_at DESC);

-- RLS
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['customer','contact','property','tag','customer_tag','customer_note'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

INSERT INTO schema_migrations(version) VALUES ('0003') ON CONFLICT (version) DO NOTHING;

COMMIT;
