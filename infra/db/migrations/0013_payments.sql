-- infra/db/migrations/0013_payments.sql
-- 0013 — Payments (Module M11 / T303). Owns: payment_provider_config, invoice,
-- payment tables. References quote_id and customer_id by logical reference only
-- (no cross-context FK — same rule as other service tables).

BEGIN;

-- Enum types
DO $$ BEGIN
  CREATE TYPE payment_provider AS ENUM ('stripe', 'square', 'ach');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE payment_status AS ENUM ('pending', 'processing', 'captured', 'failed', 'refunded', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE payment_type AS ENUM ('deposit', 'installment', 'final', 'full');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE invoice_status AS ENUM ('draft', 'issued', 'paid', 'overdue', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Per-tenant provider configuration (encrypted API keys stored in config_encrypted).
CREATE TABLE IF NOT EXISTS payment_provider_config (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  provider          payment_provider NOT NULL,
  is_active         boolean NOT NULL DEFAULT false,
  config_encrypted  text NOT NULL DEFAULT '{}',
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_tenant_provider UNIQUE (tenant_id, provider)
);
DROP TRIGGER IF EXISTS trg_payment_provider_config_touch ON payment_provider_config;
CREATE TRIGGER trg_payment_provider_config_touch BEFORE UPDATE ON payment_provider_config
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Invoice ledger — one invoice per accepted quote (or partial invoicing).
CREATE TABLE IF NOT EXISTS invoice (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  quote_id          uuid NOT NULL,
  customer_id       uuid NOT NULL,
  number            text NOT NULL,
  status            invoice_status NOT NULL DEFAULT 'draft',
  subtotal_minor    bigint NOT NULL DEFAULT 0,
  tax_minor         bigint NOT NULL DEFAULT 0,
  total_minor       bigint NOT NULL DEFAULT 0,
  amount_paid_minor bigint NOT NULL DEFAULT 0,
  amount_due_minor  bigint NOT NULL DEFAULT 0,
  currency          text NOT NULL DEFAULT 'USD',
  due_at            timestamptz,
  issued_at         timestamptz,
  paid_at           timestamptz,
  deposit_bps       int NOT NULL DEFAULT 5000,
  notes             text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_tenant_invoice_number UNIQUE (tenant_id, number)
);
DROP TRIGGER IF EXISTS trg_invoice_touch ON invoice;
CREATE TRIGGER trg_invoice_touch BEFORE UPDATE ON invoice
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Individual payment records — deposits, installments, final payments.
CREATE TABLE IF NOT EXISTS payment (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  quote_id              uuid NOT NULL,
  invoice_id            uuid REFERENCES invoice(id) ON DELETE SET NULL,
  provider              payment_provider NOT NULL,
  payment_type          payment_type NOT NULL DEFAULT 'deposit',
  status                payment_status NOT NULL DEFAULT 'pending',
  amount_minor          bigint NOT NULL,
  currency              text NOT NULL DEFAULT 'USD',
  provider_payment_id   text,
  provider_checkout_url text,
  description           text,
  failure_reason        text,
  idempotency_key       text NOT NULL UNIQUE,
  captured_at           timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_payment_touch ON payment;
CREATE TRIGGER trg_payment_touch BEFORE UPDATE ON payment
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_payment_tenant ON payment(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payment_quote ON payment(quote_id);
CREATE INDEX IF NOT EXISTS idx_payment_provider_id ON payment(provider_payment_id);
CREATE INDEX IF NOT EXISTS idx_invoice_tenant ON invoice(tenant_id);
CREATE INDEX IF NOT EXISTS idx_invoice_quote ON invoice(quote_id);
CREATE INDEX IF NOT EXISTS idx_invoice_customer ON invoice(customer_id);
CREATE INDEX IF NOT EXISTS idx_payment_provider_config_tenant ON payment_provider_config(tenant_id);

-- RLS
ALTER TABLE payment_provider_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS payment_provider_config_tenant_iso ON payment_provider_config;
CREATE POLICY payment_provider_config_tenant_iso ON payment_provider_config
  USING (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS invoice_tenant_iso ON invoice;
CREATE POLICY invoice_tenant_iso ON invoice
  USING (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS payment_tenant_iso ON payment;
CREATE POLICY payment_tenant_iso ON payment
  USING (tenant_id = app_current_tenant());

-- Track migration
INSERT INTO schema_migrations(version) VALUES ('0013')
  ON CONFLICT (version) DO NOTHING;

COMMIT;
