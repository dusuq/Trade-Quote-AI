-- TradeQuote AI — Postgres bootstrap (runs once on first container init).
-- Enables the extensions every service relies on.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";     -- gen_random_uuid(), crypt()
CREATE EXTENSION IF NOT EXISTS "citext";       -- case-insensitive emails
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- fuzzy search on names/pricebook
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector for AI memory / semantic search

-- Sanity marker so `dev:up` health checks can confirm init ran.
DO $$ BEGIN
  RAISE NOTICE 'TradeQuote AI: extensions initialized (vector, pg_trgm, pgcrypto, citext, uuid-ossp)';
END $$;
