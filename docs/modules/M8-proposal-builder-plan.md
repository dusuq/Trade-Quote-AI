# T203 — M8 Proposal Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `services/proposal-service` (currently T107's stateless PDF engine) with
persistence, templates, and delivery-status tracking, exposing a public unauthenticated view link,
and wire the web app to create/send/view proposals from a quote.

**Architecture:** Three new Postgres tables (`proposal_template`, `proposal`, `proposal_version`) in
`proposal-service`'s own database, following the Session-style pattern quote-service already uses
(direct SQLAlchemy `Session` in the application layer — conventions §3 explicitly accepts this
"provided every query is tenant-scoped and tested"). The web app assembles the full document
client-side (as T107's existing endpoint already expects) and posts it once. A new public route
resolves its tenant via a `SECURITY DEFINER` Postgres function, since RLS blocks any query with no
`app.current_tenant` set and there is no session for an unauthenticated caller to carry one.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic 2 (Python 3.12, `uv`) for the backend; Fastify
(TypeScript) for the two required gateway fixes; Next.js 15 + TanStack Query + Zod + Vitest for the
frontend.

**Spec:** [docs/modules/M8-proposal-builder.md](M8-proposal-builder.md) — read it first; this plan
implements decisions D1–D6 verbatim. Two things below go beyond the spec because they turned out to
be load-bearing prerequisites the spec didn't resolve at the code level: the gateway's exact-match
public-path allowlist (Task 1) and its binary-corrupting proxy (also Task 1).

## Global Constraints

- Money is integer minor units (`*_minor: int`, cents) + ISO-4217 currency. Never floats.
- Rates/margins are basis points (`*_bps: int`; `10000 = 100%`) — not used directly in T203's own
  tables, but any money field follows this.
- Use `datetime.now(UTC)` — `from datetime import UTC`. Never `datetime.now(timezone.utc)` (ruff
  `UP017` fails CI).
- Downstream services never decode JWTs; trust `x-tenant-id`/`x-user-id` from the gateway — **except**
  `GET /v1/proposals/{id}/view`, which is deliberately the one route with no auth at all (D4).
- Every tenant-scoped query filters `tenant_id` explicitly — RLS is defense-in-depth, not the only
  guard, because the SQLite test harness has no RLS.
- `proposal_status`'s SQLAlchemy `Enum(...)` mapping MUST declare
  `values_callable=lambda e: [m.value for m in e]` — this is the exact bug `T206b` exists to fix
  elsewhere in the codebase; get it right from the start here (spec §3 caution).
- `quote_id` on `proposal` is a logical reference, not a DB foreign key (D5) — `proposal-service`
  never calls `quote-service`.
- Route surface under `/v1/<plural-noun>`; `/health` exposed; service reachable through the gateway.
- `ruff check` and `mypy app` must be clean; `pytest` must pass; target ≥80% coverage on
  domain/application logic. `pnpm typecheck`/`pnpm test`/`pnpm build` clean for every touched
  TS package.
- Two new domain events (`proposal.document.sent`, `proposal.document.viewed`) are purely additive
  to `packages/types` — flagged for CTO audit (D6), same as the gateway changes.

---

## File Structure

```
apps/api-gateway/src/
  plugins/auth.ts              EDIT  — public-path pattern matching for /view
  plugins/proxy.ts             EDIT  — binary-safe response passthrough
  server.ts                    EDIT  — register /v1/proposal-templates
  test/auth.test.ts            EDIT  — +isPublic pattern tests
  test/server.test.ts          EDIT  — +binary passthrough test, +public /view test

infra/db/migrations/
  0006_proposal.sql            NEW   — proposal_template, proposal, proposal_version, enum,
                                        resolve_proposal_tenant() SECURITY DEFINER function, RLS

services/proposal-service/
  pyproject.toml                       EDIT  — + sqlalchemy, psycopg
  app/config.py                        EDIT  — + database_url
  app/domain/proposal.py               NEW   — ProposalStatus enum, TenantResolver Protocol,
                                                 ProposalTemplate/Proposal/ProposalVersionRecord dataclasses
  app/domain/errors.py                 EDIT  — + TemplateNotFoundError, ProposalNotFoundError
  app/domain/events.py                 EDIT  — + proposal_sent, proposal_viewed
  app/infrastructure/db.py             NEW   — engine, Base, tenant_session, PostgresTenantResolver
  app/infrastructure/models.py         NEW   — ProposalTemplateORM, ProposalORM, ProposalVersionORM
  app/application/template_services.py NEW   — template CRUD use cases
  app/application/proposal_services.py NEW   — create/send/mark-viewed use cases
  app/application/services.py          (existing, T107, unchanged)
  app/interface/schemas.py             EDIT  — + template & proposal DTOs
  app/interface/template_routes.py     NEW   — /v1/proposal-templates
  app/interface/proposal_routes.py     NEW   — /v1/proposals (create/list/get/send/view)
  app/interface/routes.py              EDIT  — becomes a thin router-of-routers
  README.md                            EDIT  — document the new endpoints
  tests/conftest.py                    EDIT  — + db_session/tenant_id fixtures (SQLite, mirrors quote-service)
  tests/fakes.py                       EDIT  — + FakeTenantResolver
  tests/test_template_services.py      NEW
  tests/test_proposal_services.py      NEW
  tests/test_proposal_routes.py        NEW   — includes the no-auth-header /view test

packages/types/src/events.ts   EDIT  — + ProposalSentPayload, ProposalViewedPayload

apps/web/src/lib/
  proposals.ts                 NEW   — types, form schema, API calls (mirrors quotes.ts)
  proposals.test.ts            NEW
  proposal-templates.ts        NEW   — template CRUD API calls
  proposal-templates.test.ts   NEW
apps/web/src/app/(app)/
  proposals/page.tsx           NEW   — list
  proposals/[id]/page.tsx      NEW   — detail: status, PDF link, "Send" button
  quotes/[id]/page.tsx         EDIT  — + "Create Proposal" button
  settings/page.tsx            EDIT  — template CRUD replaces the branding placeholder

TASKS.md                       EDIT  — check T203, refresh rollup
tracking/PROGRESS-TRACKER.csv  EDIT  — T203 row -> DONE
```

---

### Task 1: Gateway prerequisites — public-path pattern matching + binary-safe proxy

**Files:**
- Modify: `apps/api-gateway/src/plugins/auth.ts`
- Modify: `apps/api-gateway/src/plugins/proxy.ts`
- Test: `apps/api-gateway/test/auth.test.ts`
- Test: `apps/api-gateway/test/server.test.ts`

**Interfaces:**
- Produces: `isPublic(url: string): boolean` now also matches `/v1/proposals/<uuid>/view` (kept
  private to `auth.ts`, exercised only through `server.test.ts`'s full-request tests)
- Produces: `registerServiceProxy` forwards response bytes unchanged for any content type

This task fixes two problems discovered while planning T203, not introduced by it. Both must land
before any later task's public `/view` route can work end-to-end.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api-gateway/test/server.test.ts` (inside the existing `describe("api-gateway", ...)`
block, using the existing `fakeUpstream`/`testServer` helpers — add a second fake upstream that
returns raw bytes):

```typescript
  it("allows GET /v1/proposals/<uuid>/view with no token", async () => {
    const app = testServer();
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/11111111-1111-1111-1111-111111111111/view",
    });
    // The fake upstream (auth-service) doesn't implement this path, but the
    // point is it's not rejected at the gateway with 401 before even proxying.
    expect(res.statusCode).not.toBe(401);
    await app.close();
  });

  it("still rejects a non-view proposals route with no token", async () => {
    const app = testServer();
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/11111111-1111-1111-1111-111111111111",
    });
    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it("passes binary response bytes through unchanged", async () => {
    const binaryUpstream = createServer((req, res) => {
      // Bytes that are NOT valid UTF-8 on their own (a lone continuation byte) —
      // decoding+re-encoding as text would corrupt this, proving the fix works.
      const raw = Buffer.from([0x25, 0x50, 0x44, 0x46, 0xff, 0xfe, 0x00, 0x01]);
      res.writeHead(200, { "content-type": "application/pdf" });
      res.end(raw);
    });
    await new Promise<void>((resolve) => binaryUpstream.listen(0, resolve));
    const { port } = binaryUpstream.address() as AddressInfo;

    const app = buildServer({
      jwtSecret: SECRET,
      authServiceUrl: upstreamUrl,
      proposalServiceUrl: `http://127.0.0.1:${port}`,
    });
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"] });
    const res = await app.inject({
      method: "GET",
      url: "/v1/proposals/abc/pdf",
      headers: { authorization: `Bearer ${token}` },
    });
    const expected = Buffer.from([0x25, 0x50, 0x44, 0x46, 0xff, 0xfe, 0x00, 0x01]);
    expect(Buffer.compare(res.rawPayload, expected)).toBe(0);

    binaryUpstream.close();
    await app.close();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api-gateway && pnpm test`
Expected: the first new test fails with `401` (public-path set doesn't match); the third fails
because `res.rawPayload` differs from `expected` (bytes were UTF-8-decoded and re-encoded, corrupting
`0xff 0xfe`)

- [ ] **Step 3: Fix `isPublic` to support patterns, not just exact strings**

Replace the top of `apps/api-gateway/src/plugins/auth.ts`:

```typescript
/**
 * Exact paths that never require a token — registration/login happen before
 * the client has one, and /health is a liveness probe.
 */
const PUBLIC_PATHS = new Set<string>(["/health", "/v1/auth/register", "/v1/auth/login"]);

/**
 * Path *patterns* that never require a token, for routes with a dynamic
 * segment. Keep this list short and each entry narrowly scoped — a public
 * route is a route with no tenant check at all downstream, so a pattern
 * that's too broad here is a real authorization bypass, not just a bug.
 */
const PUBLIC_PATH_PATTERNS: RegExp[] = [
  // Customer-facing proposal view link — proposal-service resolves its own
  // tenant from the id; see services/proposal-service's TenantResolver.
  /^\/v1\/proposals\/[0-9a-fA-F-]+\/view$/,
];

function isPublic(url: string): boolean {
  const path = url.split("?")[0] ?? url;
  if (PUBLIC_PATHS.has(path)) return true;
  return PUBLIC_PATH_PATTERNS.some((pattern) => pattern.test(path));
}
```

- [ ] **Step 4: Fix the proxy to pass bytes through unchanged**

In `apps/api-gateway/src/plugins/proxy.ts`, replace the last three lines of the handler:

```typescript
    reply.code(upstreamResponse.status);
    const contentType = upstreamResponse.headers.get("content-type");
    if (contentType) reply.header("content-type", contentType);
    reply.send(await upstreamResponse.text());
```

with:

```typescript
    reply.code(upstreamResponse.status);
    const contentType = upstreamResponse.headers.get("content-type");
    if (contentType) reply.header("content-type", contentType);
    // Buffer, not .text() — .text() UTF-8-decodes the body, which silently
    // corrupts binary responses (PDFs). Buffer round-trips both binary and
    // text content correctly.
    reply.send(Buffer.from(await upstreamResponse.arrayBuffer()));
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api-gateway && pnpm test`
Expected: all tests pass, including the 3 new ones and every pre-existing test in `auth.test.ts` and
`server.test.ts`

- [ ] **Step 6: Typecheck**

Run: `cd apps/api-gateway && pnpm typecheck`
Expected: clean

- [ ] **Step 7: Commit**

```bash
git add apps/api-gateway/src/plugins/auth.ts apps/api-gateway/src/plugins/proxy.ts apps/api-gateway/test/auth.test.ts apps/api-gateway/test/server.test.ts
git commit -m "fix(gateway): support pattern-matched public routes; stop corrupting binary responses

Found while planning T203's public proposal-view link. Two
pre-existing gaps, not introduced by this change:
- isPublic() only matched exact strings, so no route with a dynamic
  segment (like /v1/proposals/{id}/view) could ever be public
- the proxy read every upstream response via .text(), UTF-8-decoding
  and silently corrupting any binary body — meaning T107's existing
  PDF endpoints were already broken when accessed through the gateway"
```

---

### Task 2: Migration + proposal-service DB scaffolding

**Files:**
- Create: `infra/db/migrations/0006_proposal.sql`
- Modify: `services/proposal-service/pyproject.toml`
- Modify: `services/proposal-service/app/config.py`
- Create: `services/proposal-service/app/infrastructure/db.py`

**Interfaces:**
- Produces: `Base` (SQLAlchemy `DeclarativeBase`), `engine`, `SessionLocal`
- Produces: `tenant_session(tenant_id: UUID) -> ContextManager[Session]`
- Produces: `PostgresTenantResolver` (implements `TenantResolver` from Task 3 — this task defines
  the class; Task 3's Protocol gives it a name to satisfy)

- [ ] **Step 1: Write the migration**

```sql
-- infra/db/migrations/0006_proposal.sql
-- 0006 — Proposal Builder (Module M8). Owns: proposal_template, proposal, proposal_version.
-- Extends T107's stateless PDF engine (services/proposal-service) with persistence.

BEGIN;

DO $$ BEGIN
  CREATE TYPE proposal_status AS ENUM ('draft', 'sent', 'viewed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS proposal_template (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  name                   text NOT NULL,
  company_name           text NOT NULL,
  logo_url               text,
  primary_color          text NOT NULL DEFAULT '#111827',
  phone                  text,
  email                  text,
  website                text,
  default_terms_text     text,
  default_warranty_text  text,
  is_default             boolean NOT NULL DEFAULT false,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_proposal_template_touch ON proposal_template;
CREATE TRIGGER trg_proposal_template_touch BEFORE UPDATE ON proposal_template
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
-- Only one default template per tenant, enforced at the DB level (spec §7).
CREATE UNIQUE INDEX IF NOT EXISTS proposal_template_one_default_per_tenant
  ON proposal_template (tenant_id) WHERE is_default;

CREATE TABLE IF NOT EXISTS proposal (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  quote_id          uuid NOT NULL,   -- logical reference only (spec D5); quote lives in quote-service
  template_id       uuid NOT NULL REFERENCES proposal_template(id),
  number            text NOT NULL,   -- "P-2026-000001", same scheme as quote.number
  status            proposal_status NOT NULL DEFAULT 'draft',
  current_version   int NOT NULL DEFAULT 1,
  storage_key       text,
  sent_at           timestamptz,
  viewed_at         timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, number)
);
DROP TRIGGER IF EXISTS trg_proposal_touch ON proposal;
CREATE TRIGGER trg_proposal_touch BEFORE UPDATE ON proposal
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_proposal_quote ON proposal(quote_id);
CREATE INDEX IF NOT EXISTS idx_proposal_status ON proposal(tenant_id, status);

CREATE TABLE IF NOT EXISTS proposal_version (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  proposal_id   uuid NOT NULL REFERENCES proposal(id) ON DELETE CASCADE,
  version       int NOT NULL,
  snapshot      jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (proposal_id, version)
);

-- RLS (conventions §2) — mirrors 0005_quote.sql's pattern exactly.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['proposal_template','proposal','proposal_version'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());',
      t);
  END LOOP;
END $$;

-- Resolves which tenant owns a proposal, bypassing RLS for this one narrow
-- lookup. Needed because GET /v1/proposals/{id}/view has no tenant context
-- at all — there is no session, no header, nothing to set app.current_tenant
-- from. SECURITY DEFINER makes this function run with its owner's
-- privileges (the migration-owner role, which is the proposal table's
-- owner and therefore already bypasses RLS on it) regardless of who calls
-- it. `SET search_path = public` is a standard hardening step for
-- SECURITY DEFINER functions, preventing search-path hijacking.
CREATE OR REPLACE FUNCTION resolve_proposal_tenant(p_proposal_id uuid) RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT tenant_id FROM proposal WHERE id = p_proposal_id;
$$;

INSERT INTO schema_migrations(version) VALUES ('0006') ON CONFLICT (version) DO NOTHING;

COMMIT;
```

- [ ] **Step 2: Add the new Python dependencies**

In `services/proposal-service/pyproject.toml`, add to `dependencies` (after `"qrcode[pil]>=8.0",`):

```toml
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.2",
```

- [ ] **Step 3: Add `database_url` to config**

In `services/proposal-service/app/config.py`, add inside the `Settings` class (after
`pdf_storage_dir`):

```python
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote"
```

- [ ] **Step 4: Write `infrastructure/db.py`**

```python
"""Database engine, sessions, multi-tenant RLS context, and the public
view-link tenant resolver."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Yield a database session scoped to a single tenant.
    Sets PostgreSQL GUC `app.current_tenant` (transaction-local) to enable
    RLS row isolation — mirrors quote-service's tenant_session exactly.
    """
    session = SessionLocal()
    try:
        session.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class PostgresTenantResolver:
    """Resolves which tenant owns a proposal via a SECURITY DEFINER SQL
    function that bypasses RLS for this one lookup — the caller has no
    tenant context yet, so a plain query would see zero rows under RLS.

    Untestable under the SQLite test harness (no SECURITY DEFINER support).
    Route tests inject `tests.fakes.FakeTenantResolver` instead — see
    tests/test_proposal_routes.py. This mirrors T206's pattern of an
    injectable seam around the one piece of logic only live Postgres can
    exercise.
    """

    def resolve(self, proposal_id: UUID) -> UUID | None:
        session = SessionLocal()
        try:
            result = session.execute(
                text("SELECT resolve_proposal_tenant(:pid)"), {"pid": str(proposal_id)}
            ).scalar()
            session.commit()
            return UUID(str(result)) if result else None
        finally:
            session.close()
```

- [ ] **Step 5: Verify the migration is structurally valid SQL**

Run: `cd "/d/TradeQuote AI" && python -c "
import re
sql = open('infra/db/migrations/0006_proposal.sql').read()
assert sql.count('BEGIN;') == 1 and sql.count('COMMIT;') == 1, 'transaction wrapper mismatch'
assert 'proposal_template' in sql and 'proposal_version' in sql and 'resolve_proposal_tenant' in sql
print('0006_proposal.sql: structurally OK')
"`
Expected: `0006_proposal.sql: structurally OK` (this project has no live Postgres available in this
environment to apply the migration for real — same honest gap T206 documented; structural checks
are what's achievable here)

- [ ] **Step 6: Install the new dependency and verify the service still imports**

Run: `cd services/proposal-service && uv sync && uv run python -c "from app.infrastructure.db import Base, tenant_session, PostgresTenantResolver; print('db.py imports OK')"`
Expected: `db.py imports OK`

- [ ] **Step 7: Commit**

```bash
git add infra/db/migrations/0006_proposal.sql services/proposal-service/pyproject.toml services/proposal-service/app/config.py services/proposal-service/app/infrastructure/db.py
git commit -m "feat(T203): add proposal DB migration and SQLAlchemy scaffolding"
```

---

### Task 3: Domain layer

**Files:**
- Create: `services/proposal-service/app/domain/proposal.py`
- Modify: `services/proposal-service/app/domain/errors.py`
- Modify: `services/proposal-service/app/domain/events.py`
- Test: `services/proposal-service/tests/test_domain_proposal.py`

**Interfaces:**
- Produces: `ProposalStatus(str, enum.Enum)` — `DRAFT`, `SENT`, `VIEWED`
- Produces: `ProposalTemplate`, `Proposal`, `ProposalVersionRecord` (frozen-shape dataclasses,
  field names match the DB columns in Task 2's migration exactly)
- Produces: `TenantResolver` Protocol — `.resolve(proposal_id: UUID) -> UUID | None`
- Produces: `TemplateNotFoundError`, `ProposalNotFoundError` (both `Exception` subclasses)
- Produces: `proposal_sent(tenant_id, proposal_id, quote_id, channel) -> DomainEvent`
- Produces: `proposal_viewed(tenant_id, proposal_id, viewed_at) -> DomainEvent`

- [ ] **Step 1: Write the failing tests**

```python
# services/proposal-service/tests/test_domain_proposal.py
"""Tests for the Proposal Builder's domain layer (T203 / M8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.domain.proposal import ProposalStatus
from app.domain.events import proposal_sent, proposal_viewed


def test_proposal_status_values_are_lowercase():
    # Guards against the exact T206b-class bug: the Python enum's *value*
    # (not .name) must match what the Postgres enum type declares.
    assert ProposalStatus.DRAFT.value == "draft"
    assert ProposalStatus.SENT.value == "sent"
    assert ProposalStatus.VIEWED.value == "viewed"


def test_proposal_sent_event_shape():
    tenant_id = uuid.uuid4()
    proposal_id = uuid.uuid4()
    quote_id = uuid.uuid4()
    event = proposal_sent(tenant_id, proposal_id, quote_id, channel="email")
    assert event.event_name == "proposal.document.sent"
    assert event.payload == {
        "proposalId": str(proposal_id),
        "quoteId": str(quote_id),
        "channel": "email",
    }


def test_proposal_viewed_event_shape():
    tenant_id = uuid.uuid4()
    proposal_id = uuid.uuid4()
    viewed_at = datetime.now(UTC)
    event = proposal_viewed(tenant_id, proposal_id, viewed_at)
    assert event.event_name == "proposal.document.viewed"
    assert event.payload["proposalId"] == str(proposal_id)
    assert event.payload["viewedAt"] == viewed_at.isoformat()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/proposal-service && uv run pytest tests/test_domain_proposal.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.domain.proposal'`

- [ ] **Step 3: Write `domain/proposal.py`**

```python
"""Domain entities for the Proposal Builder (M8) — persistence, templates,
and lifecycle on top of T107's stateless PDF engine. Framework-free: no
SQLAlchemy, no Pydantic (conventions §3 — customer-service is the gold
standard this follows).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class ProposalStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"


@dataclass(slots=True)
class ProposalTemplate:
    id: UUID
    tenant_id: UUID
    name: str
    company_name: str
    logo_url: str | None
    primary_color: str
    phone: str | None
    email: str | None
    website: str | None
    default_terms_text: str | None
    default_warranty_text: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Proposal:
    id: UUID
    tenant_id: UUID
    quote_id: UUID
    template_id: UUID
    number: str
    status: ProposalStatus
    current_version: int
    storage_key: str | None
    sent_at: datetime | None
    viewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ProposalVersionRecord:
    id: UUID
    tenant_id: UUID
    proposal_id: UUID
    version: int
    snapshot: dict
    created_at: datetime


class TenantResolver(Protocol):
    def resolve(self, proposal_id: UUID) -> UUID | None:
        """Return the tenant_id owning `proposal_id`, or None if it doesn't
        exist. Used only by the public /view route, which has no tenant
        context to open a normal tenant-scoped session with."""
        ...
```

- [ ] **Step 4: Add errors**

Append to `services/proposal-service/app/domain/errors.py`:

```python
class TemplateNotFoundError(Exception):
    pass


class ProposalNotFoundError(Exception):
    pass
```

- [ ] **Step 5: Add event factories**

Append to `services/proposal-service/app/domain/events.py` (and widen the `ProposalEventName`
Literal at the top of the file to include the two new names):

```python
ProposalEventName = Literal[
    "proposal.document.generated",
    "proposal.document.pdfRendered",
    "proposal.document.sent",
    "proposal.document.viewed",
]
```

```python
def proposal_sent(
    tenant_id: UUID, proposal_id: UUID, quote_id: UUID, *, channel: str
) -> DomainEvent:
    return DomainEvent(
        event_name="proposal.document.sent",
        tenant_id=tenant_id,
        payload={
            "proposalId": str(proposal_id),
            "quoteId": str(quote_id),
            "channel": channel,
        },
    )


def proposal_viewed(tenant_id: UUID, proposal_id: UUID, viewed_at: datetime) -> DomainEvent:
    return DomainEvent(
        event_name="proposal.document.viewed",
        tenant_id=tenant_id,
        payload={
            "proposalId": str(proposal_id),
            "viewedAt": viewed_at.isoformat(),
        },
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd services/proposal-service && uv run pytest tests/test_domain_proposal.py -v`
Expected: `3 passed`

- [ ] **Step 7: Lint and type-check**

Run: `cd services/proposal-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean

- [ ] **Step 8: Commit**

```bash
git add services/proposal-service/app/domain/proposal.py services/proposal-service/app/domain/errors.py services/proposal-service/app/domain/events.py services/proposal-service/tests/test_domain_proposal.py
git commit -m "feat(T203): add proposal domain layer (status, entities, events)"
```

---

### Task 4: ORM models + test fixtures

**Files:**
- Create: `services/proposal-service/app/infrastructure/models.py`
- Modify: `services/proposal-service/tests/conftest.py`
- Modify: `services/proposal-service/tests/fakes.py`

**Interfaces:**
- Consumes: `Base` (Task 2), `ProposalStatus` (Task 3)
- Produces: `ProposalTemplateORM`, `ProposalORM`, `ProposalVersionORM` (SQLAlchemy models)
- Produces: test fixtures `engine`, `db_session`, `tenant_id`, `client` (mirrors quote-service's
  `tests/conftest.py` exactly, adapted to this service)
- Produces: `FakeTenantResolver` (implements `TenantResolver`)

- [ ] **Step 1: Write the ORM models**

```python
# services/proposal-service/app/infrastructure/models.py
"""SQLAlchemy ORM models for the Proposal Builder (M8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.proposal import ProposalStatus
from app.infrastructure.db import Base


class ProposalTemplateModel(Base):
    __tablename__ = "proposal_template"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_color: Mapped[str] = mapped_column(String, nullable=False, default="#111827")
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    default_terms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_warranty_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class ProposalModel(Base):
    __tablename__ = "proposal"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="proposal_tenant_id_number_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(
            ProposalStatus,
            name="proposal_status",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ProposalStatus.DRAFT,
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    versions: Mapped[list[ProposalVersionModel]] = relationship(
        "ProposalVersionModel",
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="ProposalVersionModel.version",
    )


class ProposalVersionModel(Base):
    __tablename__ = "proposal_version"
    __table_args__ = (UniqueConstraint("proposal_id", "version", name="proposal_version_proposal_id_version_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposal.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )

    proposal: Mapped[ProposalModel] = relationship("ProposalModel", back_populates="versions")
```

- [ ] **Step 2: Add SQLite-backed test fixtures**

Replace the full contents of `services/proposal-service/tests/conftest.py`:

```python
"""Pytest configuration and fixtures for proposal-service."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.entities import (
    CompanyBranding,
    CustomerInfo,
    Money,
    ProposalDocument,
    ProposalLineItem,
)
from app.infrastructure.models import Base
from app.main import app


@pytest.fixture(scope="session")
def engine():
    db_engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=db_engine)
    yield db_engine
    Base.metadata.drop_all(bind=db_engine)


@pytest.fixture
def db_session(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_header(tenant_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-tenant-id": str(tenant_id),
        "x-user-id": str(uuid.uuid4()),
    }


@pytest.fixture
def sample_document() -> ProposalDocument:
    return ProposalDocument(
        proposal_id=uuid.uuid4(),
        quote_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        branding=CompanyBranding(
            company_name="Bright Sparks Electric",
            primary_color="#1D4ED8",
            phone="(555) 123-4567",
            email="hello@brightsparks.example",
            website="brightsparks.example",
        ),
        customer=CustomerInfo(
            display_name="Jordan Rivera",
            email="jordan@example.com",
            phone="(555) 987-6543",
            property_address="742 Evergreen Terrace, Springfield",
        ),
        line_items=[
            ProposalLineItem(
                description="Replace 200A panel",
                quantity=1,
                unit="each",
                unit_price=Money(85000, "USD"),
                line_total=Money(85000, "USD"),
            ),
            ProposalLineItem(
                description="Install LED recessed lights",
                quantity=12,
                unit="each",
                unit_price=Money(4500, "USD"),
                line_total=Money(54000, "USD"),
            ),
        ],
        subtotal=Money(139000, "USD"),
        tax=Money(12160, "USD"),
        total=Money(151160, "USD"),
        scope_of_work="Replace the main electrical panel and install 12 LED recessed lights "
        "throughout the living room and kitchen.",
        warranty_text="All labor is warrantied for 2 years from the completion date.",
        terms_text="50% deposit due at signing, balance due on completion.",
        valid_until="2026-08-15",
        qr_payload_url="https://tradequote.example/p/view",
    )
```

This moves `sample_document` here from `tests/fakes.py` unchanged, and adds `db_session`/`tenant_id`/
`client`/`auth_header`, matching quote-service's `conftest.py` shape. `Base` now comes from
`app.infrastructure.models` (which re-exports the one declared in `app.infrastructure.db`) rather
than not existing at all.

- [ ] **Step 3: Add `FakeTenantResolver`**

Append to `services/proposal-service/tests/fakes.py`:

```python
from uuid import UUID


class FakeTenantResolver:
    """Implements app.domain.proposal.TenantResolver without touching Postgres."""

    def __init__(self, mapping: dict[UUID, UUID] | None = None) -> None:
        self._mapping = mapping or {}

    def resolve(self, proposal_id: UUID) -> UUID | None:
        return self._mapping.get(proposal_id)
```

- [ ] **Step 4: Run the existing suite to check nothing broke**

Run: `cd services/proposal-service && uv run pytest -v`
Expected: `test_pdf_renderer.py` and `test_services.py`'s existing tests still pass (they use
`sample_document`, now defined in `conftest.py` instead of `fakes.py` — confirm no import breaks;
if `test_services.py` or `test_pdf_renderer.py` import `sample_document` from `tests.fakes`, update
that import to come from the fixture instead, since fixtures aren't imported, they're injected by
name)

- [ ] **Step 5: Lint and type-check**

Run: `cd services/proposal-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add services/proposal-service/app/infrastructure/models.py services/proposal-service/tests/conftest.py services/proposal-service/tests/fakes.py
git commit -m "feat(T203): add proposal ORM models and SQLite test fixtures"
```

---

### Task 5: Template application service + routes

**Files:**
- Create: `services/proposal-service/app/application/template_services.py`
- Modify: `services/proposal-service/app/interface/schemas.py`
- Create: `services/proposal-service/app/interface/template_routes.py`
- Test: `services/proposal-service/tests/test_template_services.py`

**Interfaces:**
- Consumes: `ProposalTemplateModel` (Task 4), `TemplateNotFoundError` (Task 3)
- Produces: `create_template(session, tenant_id, data: TemplateCreate) -> ProposalTemplateModel`
- Produces: `list_templates(session, tenant_id) -> list[ProposalTemplateModel]`
- Produces: `update_template(session, tenant_id, template_id, data: TemplateUpdate) -> ProposalTemplateModel`
- Produces: `TemplateCreate`, `TemplateUpdate`, `TemplateResponse` (Pydantic DTOs)
- Produces: router at prefix `/v1/proposal-templates`

- [ ] **Step 1: Write the failing tests**

```python
# services/proposal-service/tests/test_template_services.py
"""Tests for proposal template CRUD (T203 / M8)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.application import template_services
from app.domain.errors import TemplateNotFoundError
from app.interface.schemas import TemplateCreate, TemplateUpdate


def _create(db_session, tenant_id, *, name="Standard", is_default=True):
    return template_services.create_template(
        db_session,
        tenant_id,
        TemplateCreate(
            name=name,
            company_name="Bright Sparks Electric",
            primary_color="#1D4ED8",
            is_default=is_default,
        ),
    )


def test_create_template(db_session, tenant_id):
    template = _create(db_session, tenant_id)
    assert template.id is not None
    assert template.company_name == "Bright Sparks Electric"
    assert template.is_default is True


def test_list_templates_scoped_to_tenant(db_session, tenant_id):
    import uuid

    _create(db_session, tenant_id)
    other_tenant = uuid.uuid4()
    _create(db_session, other_tenant, name="Other Co")

    templates = template_services.list_templates(db_session, tenant_id)
    assert len(templates) == 1
    assert templates[0].name == "Standard"


def test_update_template(db_session, tenant_id):
    template = _create(db_session, tenant_id)
    updated = template_services.update_template(
        db_session, tenant_id, template.id, TemplateUpdate(primary_color="#000000")
    )
    assert updated.primary_color == "#000000"


def test_update_unknown_template_raises(db_session, tenant_id):
    import uuid

    with pytest.raises(TemplateNotFoundError):
        template_services.update_template(
            db_session, tenant_id, uuid.uuid4(), TemplateUpdate(primary_color="#000000")
        )


def test_only_one_default_template_per_tenant(db_session, tenant_id):
    _create(db_session, tenant_id, name="First", is_default=True)
    db_session.flush()
    with pytest.raises(IntegrityError):
        _create(db_session, tenant_id, name="Second", is_default=True)
        db_session.flush()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/proposal-service && uv run pytest tests/test_template_services.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.application.template_services'`

- [ ] **Step 3: Add the Pydantic schemas**

Append to `services/proposal-service/app/interface/schemas.py`:

```python
from datetime import datetime


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    company_name: str = Field(min_length=1, max_length=200)
    logo_url: str | None = None
    primary_color: str = "#111827"
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    default_terms_text: str | None = None
    default_warranty_text: str | None = None
    is_default: bool = False


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    logo_url: str | None = None
    primary_color: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    default_terms_text: str | None = None
    default_warranty_text: str | None = None
    is_default: bool | None = None


class TemplateResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    company_name: str
    logo_url: str | None
    primary_color: str
    phone: str | None
    email: str | None
    website: str | None
    default_terms_text: str | None
    default_warranty_text: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

(Note: `MoneyDto` etc. already import `Field`; this adds `ConfigDict` to the existing
`from pydantic import BaseModel, Field` line — change it to
`from pydantic import BaseModel, ConfigDict, Field`.)

- [ ] **Step 4: Implement `template_services.py`**

```python
# services/proposal-service/app/application/template_services.py
"""Use cases for proposal template CRUD (T203 / M8)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import TemplateNotFoundError
from app.infrastructure.models import ProposalTemplateModel
from app.interface.schemas import TemplateCreate, TemplateUpdate


def create_template(
    session: Session, tenant_id: UUID, data: TemplateCreate
) -> ProposalTemplateModel:
    template = ProposalTemplateModel(
        tenant_id=tenant_id,
        name=data.name,
        company_name=data.company_name,
        logo_url=data.logo_url,
        primary_color=data.primary_color,
        phone=data.phone,
        email=data.email,
        website=data.website,
        default_terms_text=data.default_terms_text,
        default_warranty_text=data.default_warranty_text,
        is_default=data.is_default,
    )
    session.add(template)
    session.flush()
    return template


def list_templates(session: Session, tenant_id: UUID) -> list[ProposalTemplateModel]:
    return list(
        session.scalars(
            select(ProposalTemplateModel).where(ProposalTemplateModel.tenant_id == tenant_id)
        )
    )


def _get_template(
    session: Session, tenant_id: UUID, template_id: UUID
) -> ProposalTemplateModel:
    template = session.scalar(
        select(ProposalTemplateModel).where(
            ProposalTemplateModel.id == template_id,
            ProposalTemplateModel.tenant_id == tenant_id,
        )
    )
    if not template:
        raise TemplateNotFoundError(f"Template '{template_id}' not found.")
    return template


def update_template(
    session: Session, tenant_id: UUID, template_id: UUID, data: TemplateUpdate
) -> ProposalTemplateModel:
    template = _get_template(session, tenant_id, template_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    session.flush()
    return template
```

- [ ] **Step 5: Implement `template_routes.py`**

```python
# services/proposal-service/app/interface/template_routes.py
"""HTTP routes for proposal templates. Trusts the gateway's x-tenant-id."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, status

from app.application import template_services
from app.domain.errors import TemplateNotFoundError
from app.infrastructure.db import tenant_session
from app.interface.schemas import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(prefix="/v1/proposal-templates", tags=["proposal-templates"])


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateCreate, x_tenant_id: str | None = Header(default=None)
) -> TemplateResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        template = template_services.create_template(session, tenant_id, body)
        return TemplateResponse.model_validate(template)


@router.get("", response_model=list[TemplateResponse])
def list_templates(x_tenant_id: str | None = Header(default=None)) -> list[TemplateResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        templates = template_services.list_templates(session, tenant_id)
        return [TemplateResponse.model_validate(t) for t in templates]


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    x_tenant_id: str | None = Header(default=None),
) -> TemplateResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            template = template_services.update_template(session, tenant_id, template_id, body)
            return TemplateResponse.model_validate(template)
    except TemplateNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd services/proposal-service && uv run pytest tests/test_template_services.py -v`
Expected: `5 passed`

- [ ] **Step 7: Lint and type-check**

Run: `cd services/proposal-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean

- [ ] **Step 8: Commit**

```bash
git add services/proposal-service/app/application/template_services.py services/proposal-service/app/interface/schemas.py services/proposal-service/app/interface/template_routes.py services/proposal-service/tests/test_template_services.py
git commit -m "feat(T203): add proposal template CRUD"
```

---

### Task 6: Proposal application service (create / send / mark-viewed)

**Files:**
- Create: `services/proposal-service/app/application/proposal_services.py`
- Modify: `services/proposal-service/app/interface/schemas.py`
- Test: `services/proposal-service/tests/test_proposal_services.py`

**Interfaces:**
- Consumes: `ProposalModel`, `ProposalVersionModel`, `ProposalTemplateModel` (Task 4);
  `ProposalStatus` (Task 3); `render_and_store_proposal_pdf` (existing, T107,
  `app.application.services`); `proposal_sent`, `proposal_viewed` (Task 3)
- Produces: `generate_proposal_number(session, tenant_id) -> str`
- Produces: `create_proposal(session, storage, tenant_id, data: ProposalCreate) -> tuple[ProposalModel, list[DomainEvent]]`
- Produces: `send_proposal(session, tenant_id, proposal_id, *, channel="email") -> tuple[ProposalModel, DomainEvent]`
- Produces: `mark_viewed_and_fetch_pdf(session, storage, tenant_id, proposal_id) -> tuple[bytes, DomainEvent | None]`
  — `DomainEvent | None` because a second view must NOT re-emit `proposal.document.viewed`

- [ ] **Step 1: Write the failing tests**

```python
# services/proposal-service/tests/test_proposal_services.py
"""Tests for proposal create/send/view use cases (T203 / M8)."""

from __future__ import annotations

import uuid

import pytest

from app.application import proposal_services, template_services
from app.domain.errors import ProposalNotFoundError
from app.domain.proposal import ProposalStatus
from app.infrastructure.models import ProposalModel
from app.interface.schemas import (
    CompanyBrandingDto,
    CustomerInfoDto,
    LineItemDto,
    MoneyDto,
    ProposalCreate,
    TemplateCreate,
)
from tests.fakes import FakePdfStorage


def _make_template(db_session, tenant_id):
    return template_services.create_template(
        db_session,
        tenant_id,
        TemplateCreate(name="Standard", company_name="Bright Sparks Electric", is_default=True),
    )


def _create_payload(template_id) -> ProposalCreate:
    return ProposalCreate(
        quote_id=uuid.uuid4(),
        template_id=template_id,
        branding=CompanyBrandingDto(company_name="Bright Sparks Electric"),
        customer=CustomerInfoDto(display_name="Jordan Rivera"),
        line_items=[
            LineItemDto(
                description="Replace 200A panel",
                quantity=1,
                unit="each",
                unit_price=MoneyDto(amount_minor=85000),
                line_total=MoneyDto(amount_minor=85000),
            )
        ],
        subtotal=MoneyDto(amount_minor=85000),
        tax=MoneyDto(amount_minor=0),
        total=MoneyDto(amount_minor=85000),
        scope_of_work="Replace the main electrical panel.",
    )


def test_create_proposal_renders_v1_and_persists(db_session, tenant_id):
    template = _make_template(db_session, tenant_id)
    storage = FakePdfStorage()

    proposal, events = proposal_services.create_proposal(
        db_session, storage, tenant_id, _create_payload(template.id)
    )

    assert proposal.id is not None
    assert proposal.number.startswith("P-")
    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.current_version == 1
    assert proposal.storage_key == f"proposals/{proposal.id}.pdf"
    assert len(storage.read(tenant_id, proposal.storage_key)) > 0

    versions = proposal_services.list_versions(db_session, tenant_id, proposal.id)
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].snapshot["customer"]["display_name"] == "Jordan Rivera"

    event_names = {e.event_name for e in events}
    assert event_names == {"proposal.document.generated", "proposal.document.pdfRendered"}


def test_send_proposal_transitions_status(db_session, tenant_id):
    template = _make_template(db_session, tenant_id)
    storage = FakePdfStorage()
    proposal, _ = proposal_services.create_proposal(
        db_session, storage, tenant_id, _create_payload(template.id)
    )

    sent, event = proposal_services.send_proposal(db_session, tenant_id, proposal.id, channel="email")

    assert sent.status == ProposalStatus.SENT
    assert sent.sent_at is not None
    assert event.event_name == "proposal.document.sent"


def test_send_unknown_proposal_raises(db_session, tenant_id):
    with pytest.raises(ProposalNotFoundError):
        proposal_services.send_proposal(db_session, tenant_id, uuid.uuid4(), channel="email")


def test_mark_viewed_transitions_status_and_emits_once(db_session, tenant_id):
    template = _make_template(db_session, tenant_id)
    storage = FakePdfStorage()
    proposal, _ = proposal_services.create_proposal(
        db_session, storage, tenant_id, _create_payload(template.id)
    )
    proposal_services.send_proposal(db_session, tenant_id, proposal.id, channel="email")

    pdf_bytes, event = proposal_services.mark_viewed_and_fetch_pdf(
        db_session, storage, tenant_id, proposal.id
    )
    assert len(pdf_bytes) > 0
    assert event is not None
    assert event.event_name == "proposal.document.viewed"

    reloaded = db_session.get(ProposalModel, proposal.id)
    assert reloaded.status == ProposalStatus.VIEWED
    first_viewed_at = reloaded.viewed_at
    assert first_viewed_at is not None

    # Second view: status stays VIEWED, viewed_at does not re-stamp, no event.
    _pdf_bytes_2, event_2 = proposal_services.mark_viewed_and_fetch_pdf(
        db_session, storage, tenant_id, proposal.id
    )
    assert event_2 is None
    reloaded_again = db_session.get(ProposalModel, proposal.id)
    assert reloaded_again.viewed_at == first_viewed_at
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/proposal-service && uv run pytest tests/test_proposal_services.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.application.proposal_services'`
(also expect `ImportError` for `ProposalCreate` — added in Step 3 below)

- [ ] **Step 3: Add the `ProposalCreate`/`ProposalResponse` schemas**

Append to `services/proposal-service/app/interface/schemas.py`:

```python
class ProposalCreate(BaseModel):
    quote_id: UUID
    template_id: UUID
    branding: CompanyBrandingDto
    customer: CustomerInfoDto
    line_items: list[LineItemDto]
    subtotal: MoneyDto
    tax: MoneyDto
    total: MoneyDto
    scope_of_work: str = Field(min_length=1)
    warranty_text: str | None = None
    terms_text: str | None = None
    valid_until: str | None = None
    qr_payload_url: str | None = None


class ProposalVersionResponse(BaseModel):
    id: UUID
    version: int
    snapshot: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    quote_id: UUID
    template_id: UUID
    number: str
    status: str
    current_version: int
    storage_key: str | None
    sent_at: datetime | None
    viewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalSendRequest(BaseModel):
    channel: str = Field(default="email", description="email, sms, or link")
```

- [ ] **Step 4: Implement `proposal_services.py`**

```python
# services/proposal-service/app/application/proposal_services.py
"""Use cases for proposal create/send/view (T203 / M8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services import render_and_store_proposal_pdf
from app.domain.entities import (
    CompanyBranding,
    CustomerInfo,
    Money,
    ProposalDocument,
    ProposalLineItem,
)
from app.domain.errors import ProposalNotFoundError
from app.domain.events import DomainEvent, proposal_sent, proposal_viewed
from app.domain.proposal import ProposalStatus
from app.domain.storage import PdfStorage
from app.infrastructure.models import ProposalModel, ProposalVersionModel
from app.interface.schemas import ProposalCreate


def generate_proposal_number(session: Session, tenant_id: uuid.UUID) -> str:
    """Sequential proposal number e.g. P-2026-000001 per tenant — same scheme
    as quote-service's generate_quote_number."""
    year = datetime.now(UTC).year
    count = session.scalar(
        select(func.count(ProposalModel.id)).where(ProposalModel.tenant_id == tenant_id)
    ) or 0
    seq = count + 1
    return f"P-{year}-{seq:06d}"


def _to_document(tenant_id: uuid.UUID, proposal_id: uuid.UUID, data: ProposalCreate) -> ProposalDocument:
    return ProposalDocument(
        proposal_id=proposal_id,
        quote_id=data.quote_id,
        tenant_id=tenant_id,
        branding=CompanyBranding(
            company_name=data.branding.company_name,
            logo_path=data.branding.logo_path,
            primary_color=data.branding.primary_color,
            phone=data.branding.phone,
            email=data.branding.email,
            website=data.branding.website,
        ),
        customer=CustomerInfo(
            display_name=data.customer.display_name,
            email=data.customer.email,
            phone=data.customer.phone,
            property_address=data.customer.property_address,
        ),
        line_items=[
            ProposalLineItem(
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=Money(item.unit_price.amount_minor, item.unit_price.currency),
                line_total=Money(item.line_total.amount_minor, item.line_total.currency),
            )
            for item in data.line_items
        ],
        subtotal=Money(data.subtotal.amount_minor, data.subtotal.currency),
        tax=Money(data.tax.amount_minor, data.tax.currency),
        total=Money(data.total.amount_minor, data.total.currency),
        scope_of_work=data.scope_of_work,
        warranty_text=data.warranty_text,
        terms_text=data.terms_text,
        valid_until=data.valid_until,
        qr_payload_url=data.qr_payload_url,
    )


def _document_to_snapshot(doc: ProposalDocument) -> dict:
    return {
        "customer": {
            "display_name": doc.customer.display_name,
            "email": doc.customer.email,
            "phone": doc.customer.phone,
            "property_address": doc.customer.property_address,
        },
        "line_items": [
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit": item.unit,
                "unit_price_minor": item.unit_price.amount_minor,
                "line_total_minor": item.line_total.amount_minor,
            }
            for item in doc.line_items
        ],
        "subtotal_minor": doc.subtotal.amount_minor,
        "tax_minor": doc.tax.amount_minor,
        "total_minor": doc.total.amount_minor,
        "scope_of_work": doc.scope_of_work,
        "warranty_text": doc.warranty_text,
        "terms_text": doc.terms_text,
    }


def create_proposal(
    session: Session,
    storage: PdfStorage,
    tenant_id: uuid.UUID,
    data: ProposalCreate,
) -> tuple[ProposalModel, list[DomainEvent]]:
    proposal_id = uuid.uuid4()
    doc = _to_document(tenant_id, proposal_id, data)

    storage_key, _pdf_bytes, events = render_and_store_proposal_pdf(
        storage, doc, template_id=data.template_id
    )

    proposal = ProposalModel(
        id=proposal_id,
        tenant_id=tenant_id,
        quote_id=data.quote_id,
        template_id=data.template_id,
        number=generate_proposal_number(session, tenant_id),
        status=ProposalStatus.DRAFT,
        current_version=1,
        storage_key=storage_key,
    )
    session.add(proposal)
    session.flush()

    version = ProposalVersionModel(
        tenant_id=tenant_id,
        proposal_id=proposal.id,
        version=1,
        snapshot=_document_to_snapshot(doc),
    )
    session.add(version)
    session.flush()

    return proposal, events


def get_proposal(session: Session, tenant_id: uuid.UUID, proposal_id: uuid.UUID) -> ProposalModel:
    proposal = session.scalar(
        select(ProposalModel).where(
            ProposalModel.id == proposal_id,
            ProposalModel.tenant_id == tenant_id,
        )
    )
    if not proposal:
        raise ProposalNotFoundError(f"Proposal '{proposal_id}' not found.")
    return proposal


def send_proposal(
    session: Session, tenant_id: uuid.UUID, proposal_id: uuid.UUID, *, channel: str
) -> tuple[ProposalModel, DomainEvent]:
    proposal = get_proposal(session, tenant_id, proposal_id)
    proposal.status = ProposalStatus.SENT
    proposal.sent_at = datetime.now(UTC)
    session.flush()
    event = proposal_sent(tenant_id, proposal.id, proposal.quote_id, channel=channel)
    return proposal, event


def mark_viewed_and_fetch_pdf(
    session: Session, storage: PdfStorage, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> tuple[bytes, DomainEvent | None]:
    """Fetch the PDF and, on the first view only, transition SENT -> VIEWED
    and emit proposal.document.viewed. A repeat view returns the PDF again
    with no status change and no second event."""
    proposal = get_proposal(session, tenant_id, proposal_id)
    pdf_bytes = storage.read(tenant_id, proposal.storage_key)

    event: DomainEvent | None = None
    if proposal.status != ProposalStatus.VIEWED:
        proposal.status = ProposalStatus.VIEWED
        proposal.viewed_at = datetime.now(UTC)
        session.flush()
        event = proposal_viewed(tenant_id, proposal.id, proposal.viewed_at)

    return pdf_bytes, event


def list_versions(
    session: Session, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> list[ProposalVersionModel]:
    return list(
        session.scalars(
            select(ProposalVersionModel).where(
                ProposalVersionModel.tenant_id == tenant_id,
                ProposalVersionModel.proposal_id == proposal_id,
            )
        )
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/proposal-service && uv run pytest tests/test_proposal_services.py -v`
Expected: `4 passed`

- [ ] **Step 6: Run the full suite to check for regressions**

Run: `cd services/proposal-service && uv run pytest -v`
Expected: all tests pass (existing T107 tests + Tasks 3/5/6's new tests)

- [ ] **Step 7: Lint and type-check**

Run: `cd services/proposal-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean

- [ ] **Step 8: Commit**

```bash
git add services/proposal-service/app/application/proposal_services.py services/proposal-service/app/interface/schemas.py services/proposal-service/tests/test_proposal_services.py
git commit -m "feat(T203): add proposal create/send/mark-viewed use cases"
```

---

### Task 7: Proposal routes (incl. public `/view`), router assembly, gateway registration, README

**Files:**
- Create: `services/proposal-service/app/interface/proposal_routes.py`
- Modify: `services/proposal-service/app/interface/routes.py`
- Modify: `apps/api-gateway/src/server.ts`
- Modify: `services/proposal-service/README.md`
- Test: `services/proposal-service/tests/test_proposal_routes.py`

**Interfaces:**
- Consumes: `proposal_services.*` (Task 6), `TenantResolver`/`FakeTenantResolver` (Tasks 3/4),
  `PostgresTenantResolver` (Task 2)
- Produces: routes `POST/GET /v1/proposals`, `GET /v1/proposals/{id}`,
  `POST /v1/proposals/{id}/send`, `GET /v1/proposals/{id}/view` (public)

- [ ] **Step 1: Write the failing tests**

```python
# services/proposal-service/tests/test_proposal_routes.py
"""Route-level tests for the Proposal Builder (T203 / M8), including the
public /view route — the one route in this codebase with no auth header."""

from __future__ import annotations

import uuid

from app.application import proposal_services, template_services
from app.interface import proposal_routes
from app.interface.schemas import (
    CompanyBrandingDto,
    CustomerInfoDto,
    LineItemDto,
    MoneyDto,
    ProposalCreate,
    TemplateCreate,
)
from tests.fakes import FakePdfStorage, FakeTenantResolver


def _create_via_services(db_session, tenant_id, storage):
    template = template_services.create_template(
        db_session,
        tenant_id,
        TemplateCreate(name="Standard", company_name="Bright Sparks Electric", is_default=True),
    )
    payload = ProposalCreate(
        quote_id=uuid.uuid4(),
        template_id=template.id,
        branding=CompanyBrandingDto(company_name="Bright Sparks Electric"),
        customer=CustomerInfoDto(display_name="Jordan Rivera"),
        line_items=[
            LineItemDto(
                description="Replace 200A panel",
                quantity=1,
                unit="each",
                unit_price=MoneyDto(amount_minor=85000),
                line_total=MoneyDto(amount_minor=85000),
            )
        ],
        subtotal=MoneyDto(amount_minor=85000),
        tax=MoneyDto(amount_minor=0),
        total=MoneyDto(amount_minor=85000),
        scope_of_work="Replace the main electrical panel.",
    )
    proposal, _events = proposal_services.create_proposal(db_session, storage, tenant_id, payload)
    proposal_services.send_proposal(db_session, tenant_id, proposal.id, channel="email")
    return proposal


def test_view_route_succeeds_with_no_tenant_header(client, monkeypatch, db_session, tenant_id):
    """The critical guarantee of D4: no x-tenant-id, no bearer token — just
    the proposal id in the URL — must still work."""
    storage = FakePdfStorage()
    proposal = _create_via_services(db_session, tenant_id, storage)

    monkeypatch.setattr(proposal_routes, "_storage", storage)
    monkeypatch.setattr(
        proposal_routes, "_tenant_resolver", FakeTenantResolver({proposal.id: tenant_id})
    )
    monkeypatch.setattr(
        "app.infrastructure.db.SessionLocal", lambda: db_session, raising=False
    )

    response = client.get(f"/v1/proposals/{proposal.id}/view")
    # No Authorization header, no x-tenant-id header, at all.
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


def test_view_route_unknown_proposal_returns_404(client, monkeypatch):
    monkeypatch.setattr(proposal_routes, "_tenant_resolver", FakeTenantResolver({}))
    response = client.get(f"/v1/proposals/{uuid.uuid4()}/view")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/proposal-service && uv run pytest tests/test_proposal_routes.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.interface.proposal_routes'`

- [ ] **Step 3: Implement `proposal_routes.py`**

```python
# services/proposal-service/app/interface/proposal_routes.py
"""HTTP routes for proposals. Every route except /view trusts the gateway's
x-tenant-id — /view is the one deliberately public route in this codebase
(spec D4): a customer opening their proposal link has no session at all.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.application import proposal_services
from app.config import settings
from app.domain.errors import ProposalNotFoundError
from app.domain.proposal import TenantResolver
from app.infrastructure.db import PostgresTenantResolver, tenant_session
from app.infrastructure.local_storage import LocalFileStorage
from app.interface.schemas import (
    ProposalCreate,
    ProposalResponse,
    ProposalSendRequest,
    ProposalVersionResponse,
)

router = APIRouter(prefix="/v1/proposals", tags=["proposals"])

_storage = LocalFileStorage(settings.pdf_storage_dir)
_tenant_resolver: TenantResolver = PostgresTenantResolver()


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


@router.post("", response_model=ProposalResponse, status_code=status.HTTP_201_CREATED)
def create_proposal(
    body: ProposalCreate, x_tenant_id: str | None = Header(default=None)
) -> ProposalResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        proposal, _events = proposal_services.create_proposal(session, _storage, tenant_id, body)
        # TODO(outbox): persist _events once a transactional outbox exists
        # (matches the exact TODO already left by T107's render_pdf route).
        return ProposalResponse.model_validate(proposal)


@router.get("/{proposal_id}", response_model=ProposalResponse)
def get_proposal(
    proposal_id: uuid.UUID, x_tenant_id: str | None = Header(default=None)
) -> ProposalResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            proposal = proposal_services.get_proposal(session, tenant_id, proposal_id)
            return ProposalResponse.model_validate(proposal)
    except ProposalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{proposal_id}/versions", response_model=list[ProposalVersionResponse])
def list_versions(
    proposal_id: uuid.UUID, x_tenant_id: str | None = Header(default=None)
) -> list[ProposalVersionResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        versions = proposal_services.list_versions(session, tenant_id, proposal_id)
        return [ProposalVersionResponse.model_validate(v) for v in versions]


@router.post("/{proposal_id}/send", response_model=ProposalResponse)
def send_proposal(
    proposal_id: uuid.UUID,
    body: ProposalSendRequest | None = None,
    x_tenant_id: str | None = Header(default=None),
) -> ProposalResponse:
    tenant_id = _require_tenant(x_tenant_id)
    channel = body.channel if body else "email"
    try:
        with tenant_session(tenant_id) as session:
            proposal, _event = proposal_services.send_proposal(
                session, tenant_id, proposal_id, channel=channel
            )
            return ProposalResponse.model_validate(proposal)
    except ProposalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{proposal_id}/view")
def view_proposal(proposal_id: uuid.UUID) -> Response:
    """Public — no headers required, no auth of any kind. Resolves its own
    tenant via _tenant_resolver, which bypasses RLS through a narrow
    SECURITY DEFINER function (see infrastructure/db.py)."""
    tenant_id = _tenant_resolver.resolve(proposal_id)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    try:
        with tenant_session(tenant_id) as session:
            pdf_bytes, _event = proposal_services.mark_viewed_and_fetch_pdf(
                session, _storage, tenant_id, proposal_id
            )
    except ProposalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found") from exc
    return Response(content=pdf_bytes, media_type="application/pdf")
```

- [ ] **Step 4: Wire `routes.py` as a router-of-routers**

Replace the full contents of `services/proposal-service/app/interface/routes.py`'s router
definition — keep the existing `/pdf` handlers (T107) exactly as they are, just change how the
module-level `router` is assembled at the bottom of the file:

```python
# At the top, alongside the existing router = APIRouter(prefix="/v1/proposals", tags=["proposals"]):
# ...existing T107 imports and the two /pdf routes stay exactly as-is on this `router`...

# At the very end of the file, after the existing render_pdf/get_pdf handlers:
from app.interface.proposal_routes import router as proposal_crud_router
from app.interface.template_routes import router as template_router

router.include_router(proposal_crud_router)
```

Wait — both `router` (T107's, prefix `/v1/proposals`) and `proposal_crud_router` (Task 7's, also
prefix `/v1/proposals`) share the same prefix. Including one router inside another that shares the
same prefix double-prefixes the path (`/v1/proposals/v1/proposals/...`). Instead, `app/main.py`
should include **three** separate routers directly, all under the same top-level app, rather than
nesting:

In `services/proposal-service/app/main.py`, replace:

```python
from app.interface.routes import router as proposal_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(proposal_router)
```

with:

```python
from app.interface.proposal_routes import router as proposal_router
from app.interface.routes import router as pdf_router
from app.interface.template_routes import router as template_router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(pdf_router)
app.include_router(proposal_router)
app.include_router(template_router)
```

`app/interface/routes.py` keeps its existing content completely unchanged (T107's `/pdf` routes,
still on a router with `prefix="/v1/proposals"`) — this task does not touch it at all beyond this
plan initially assuming otherwise. FastAPI merges routes from multiple `APIRouter`s sharing the same
app cleanly; there is no double-prefix issue as long as each router is included once, directly, at
the app level — the router-of-routers idea from the spec is unnecessary complexity given three flat
`include_router` calls achieve the same result more simply. (This is a deliberate simplification
from the spec's file-structure sketch, applied because writing it out revealed the nesting approach
would double-prefix; noting it here rather than silently deviating.)

- [ ] **Step 5: Register the gateway route for `/v1/proposal-templates`**

In `apps/api-gateway/src/server.ts`, add one line after the existing `/v1/proposals` registration:

```typescript
  registerServiceProxy(app, { prefix: "/v1/proposal-templates", upstream: cfg.proposalServiceUrl });
```

(`/v1/proposals` is already registered from T107 and already covers `/v1/proposals/{id}/view` — no
change needed there beyond Task 1's `isPublic` fix.)

- [ ] **Step 6: Update `services/proposal-service/README.md`**

Add a new `## Endpoints (v1)` section documenting the templates and proposals routes (mirroring
`quote-service/README.md`'s table format), and update the file's opening description — it currently
describes only T107's PDF engine; note that persistence, templates, and lifecycle now live here too,
with a link to `docs/modules/M8-proposal-builder.md`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd services/proposal-service && uv run pytest -v`
Expected: all tests pass, including the two new route tests

- [ ] **Step 8: Lint, type-check, and run the conventions guard**

Run: `cd services/proposal-service && uv run ruff check app tests && uv run mypy app`
Expected: both clean

Run: `cd "/d/TradeQuote AI" && python scripts/check_conventions.py`
Expected: passes (no `jwt` import added; ruff/mypy config already present)

- [ ] **Step 9: Typecheck the gateway**

Run: `cd apps/api-gateway && pnpm typecheck`
Expected: clean

- [ ] **Step 10: Commit**

```bash
git add services/proposal-service/app/interface/proposal_routes.py services/proposal-service/app/main.py services/proposal-service/app/application/proposal_services.py services/proposal-service/README.md apps/api-gateway/src/server.ts
git commit -m "feat(T203): add proposal CRUD/send/view routes, register with gateway"
```

---

### Task 8: Domain events in `packages/types`

**Files:**
- Modify: `packages/types/src/events.ts`

**Interfaces:**
- Produces: `ProposalSentPayload`, `ProposalViewedPayload` (TypeScript interfaces)
- Produces: `"proposal.document.sent"`, `"proposal.document.viewed"` registered in
  `DomainEventPayloadMap` and the `DomainEventName` union

This is the `packages/types` change flagged for CTO audit in spec D6. Purely additive — no existing
interface or union member changes.

- [ ] **Step 1: Add the payload interfaces**

In `packages/types/src/events.ts`, after the existing `ProposalPdfRenderedPayload` (around line 162,
just before the `// esign` comment):

```typescript
export interface ProposalSentPayload {
  proposalId: UUID;
  quoteId: UUID;
  channel: "email" | "sms" | "link";
}
export interface ProposalViewedPayload {
  proposalId: UUID;
  viewedAt: ISODateTime;
}
```

- [ ] **Step 2: Register in the payload map and name union**

Find the `DomainEventPayloadMap` entries for `"proposal.document.generated"` and
`"proposal.document.pdfRendered"` (around line 226) and add immediately after:

```typescript
  "proposal.document.sent": ProposalSentPayload;
  "proposal.document.viewed": ProposalViewedPayload;
```

If `DomainEventName` is a derived type (e.g. `keyof DomainEventPayloadMap`), no separate union edit
is needed — check how `DomainEventName` is defined in this file before assuming; if it is instead a
hand-written string-literal union, add the two new names there too, in the same position.

- [ ] **Step 3: Build and typecheck the package**

Run: `cd packages/types && pnpm build && pnpm typecheck`
Expected: both clean, no errors

- [ ] **Step 4: Rebuild any workspace package that depends on `@tradequote/types`**

Run: `cd "/d/TradeQuote AI" && pnpm --filter @tradequote/types build`
Expected: succeeds (this makes the new types available to `apps/web` if it ever imports them
directly; the Python side does not consume this package, so no other rebuild is needed)

- [ ] **Step 5: Commit**

```bash
git add packages/types/src/events.ts
git commit -m "feat(T203): register proposal.document.sent/.viewed in the shared event registry

Purely additive - no existing interface or union member changes.
Flagged for CTO audit per spec D6, same as every packages/types
touch outside Agent 1's own work."
```

---

### Task 9: Web data layer (`proposals.ts`, `proposal-templates.ts`)

**Files:**
- Create: `apps/web/src/lib/proposals.ts`
- Create: `apps/web/src/lib/proposals.test.ts`
- Create: `apps/web/src/lib/proposal-templates.ts`
- Create: `apps/web/src/lib/proposal-templates.test.ts`

**Interfaces:**
- Consumes: `apiFetch<T>(path, options?)` (existing, `api-client.ts`)
- Produces: `Proposal`, `ProposalVersion` types; `createProposal`, `listProposals`, `getProposal`,
  `sendProposal`
- Produces: `ProposalTemplate` type; `listTemplates`, `createTemplate`, `updateTemplate`

- [ ] **Step 1: Write the failing tests**

```typescript
// apps/web/src/lib/proposals.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createProposal,
  getProposal,
  listProposals,
  sendProposal,
  statusBadgeVariantForProposal,
  type CreateProposalInput,
} from "@/lib/proposals";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(body),
    }),
  );
}

const SAMPLE_PROPOSAL = {
  id: "22222222-2222-2222-2222-222222222222",
  tenant_id: "11111111-1111-1111-1111-111111111111",
  quote_id: "33333333-3333-3333-3333-333333333333",
  template_id: "44444444-4444-4444-4444-444444444444",
  number: "P-2026-000001",
  status: "draft",
  current_version: 1,
  storage_key: "proposals/22222222.pdf",
  sent_at: null,
  viewed_at: null,
  created_at: "2026-07-26T00:00:00Z",
  updated_at: "2026-07-26T00:00:00Z",
};

describe("proposals API calls", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("createProposal posts to /v1/proposals", async () => {
    mockFetchOnce(201, SAMPLE_PROPOSAL);
    const input: CreateProposalInput = {
      quote_id: "33333333-3333-3333-3333-333333333333",
      template_id: "44444444-4444-4444-4444-444444444444",
      branding: { company_name: "Bright Sparks Electric" },
      customer: { display_name: "Jordan Rivera" },
      line_items: [],
      subtotal_minor: 0,
      tax_minor: 0,
      total_minor: 0,
      currency: "USD",
      scope_of_work: "Test scope",
    };
    const result = await createProposal("tok", input);
    expect(result.number).toBe("P-2026-000001");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/proposals");
    expect(call[1]?.method).toBe("POST");
  });

  it("listProposals gets /v1/proposals", async () => {
    mockFetchOnce(200, [SAMPLE_PROPOSAL]);
    const result = await listProposals("tok");
    expect(result).toHaveLength(1);
  });

  it("getProposal gets /v1/proposals/:id", async () => {
    mockFetchOnce(200, SAMPLE_PROPOSAL);
    const result = await getProposal("tok", SAMPLE_PROPOSAL.id);
    expect(result.id).toBe(SAMPLE_PROPOSAL.id);
  });

  it("sendProposal posts to /v1/proposals/:id/send", async () => {
    mockFetchOnce(200, { ...SAMPLE_PROPOSAL, status: "sent" });
    const result = await sendProposal("tok", SAMPLE_PROPOSAL.id, "email");
    expect(result.status).toBe("sent");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain(`/v1/proposals/${SAMPLE_PROPOSAL.id}/send`);
  });
});

describe("statusBadgeVariantForProposal", () => {
  it("maps viewed to default", () => {
    expect(statusBadgeVariantForProposal("viewed")).toBe("default");
  });
  it("maps sent to default", () => {
    expect(statusBadgeVariantForProposal("sent")).toBe("default");
  });
  it("maps draft to warning", () => {
    expect(statusBadgeVariantForProposal("draft")).toBe("warning");
  });
});
```

```typescript
// apps/web/src/lib/proposal-templates.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { createTemplate, listTemplates, updateTemplate } from "@/lib/proposal-templates";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(body),
    }),
  );
}

const SAMPLE_TEMPLATE = {
  id: "55555555-5555-5555-5555-555555555555",
  tenant_id: "11111111-1111-1111-1111-111111111111",
  name: "Standard",
  company_name: "Bright Sparks Electric",
  logo_url: null,
  primary_color: "#111827",
  phone: null,
  email: null,
  website: null,
  default_terms_text: null,
  default_warranty_text: null,
  is_default: true,
  created_at: "2026-07-26T00:00:00Z",
  updated_at: "2026-07-26T00:00:00Z",
};

describe("proposal-templates API calls", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listTemplates gets /v1/proposal-templates", async () => {
    mockFetchOnce(200, [SAMPLE_TEMPLATE]);
    const result = await listTemplates("tok");
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Standard");
  });

  it("createTemplate posts to /v1/proposal-templates", async () => {
    mockFetchOnce(201, SAMPLE_TEMPLATE);
    const result = await createTemplate("tok", { name: "Standard", company_name: "Bright Sparks Electric" });
    expect(result.id).toBe(SAMPLE_TEMPLATE.id);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[1]?.method).toBe("POST");
  });

  it("updateTemplate puts to /v1/proposal-templates/:id", async () => {
    mockFetchOnce(200, { ...SAMPLE_TEMPLATE, primary_color: "#000000" });
    const result = await updateTemplate("tok", SAMPLE_TEMPLATE.id, { primary_color: "#000000" });
    expect(result.primary_color).toBe("#000000");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain(`/v1/proposal-templates/${SAMPLE_TEMPLATE.id}`);
    expect(call[1]?.method).toBe("PUT");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- proposals.test.ts proposal-templates.test.ts`
Expected: `FAIL` — cannot find module `@/lib/proposals` / `@/lib/proposal-templates`

- [ ] **Step 3: Implement `proposal-templates.ts`**

```typescript
// apps/web/src/lib/proposal-templates.ts
import { apiFetch } from "@/lib/api-client";

export interface ProposalTemplate {
  id: string;
  tenant_id: string;
  name: string;
  company_name: string;
  logo_url: string | null;
  primary_color: string;
  phone: string | null;
  email: string | null;
  website: string | null;
  default_terms_text: string | null;
  default_warranty_text: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface TemplateInput {
  name: string;
  company_name: string;
  logo_url?: string | null;
  primary_color?: string;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
  default_terms_text?: string | null;
  default_warranty_text?: string | null;
  is_default?: boolean;
}

export function listTemplates(token: string): Promise<ProposalTemplate[]> {
  return apiFetch<ProposalTemplate[]>("/v1/proposal-templates", { token });
}

export function createTemplate(token: string, input: TemplateInput): Promise<ProposalTemplate> {
  return apiFetch<ProposalTemplate>("/v1/proposal-templates", {
    method: "POST",
    token,
    body: input,
  });
}

export function updateTemplate(
  token: string,
  templateId: string,
  input: Partial<TemplateInput>,
): Promise<ProposalTemplate> {
  return apiFetch<ProposalTemplate>(`/v1/proposal-templates/${templateId}`, {
    method: "PUT",
    token,
    body: input,
  });
}
```

- [ ] **Step 4: Implement `proposals.ts`**

```typescript
// apps/web/src/lib/proposals.ts
import { apiFetch } from "@/lib/api-client";

export interface Proposal {
  id: string;
  tenant_id: string;
  quote_id: string;
  template_id: string;
  number: string;
  status: "draft" | "sent" | "viewed";
  current_version: number;
  storage_key: string | null;
  sent_at: string | null;
  viewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProposalVersion {
  id: string;
  version: number;
  snapshot: Record<string, unknown>;
  created_at: string;
}

interface MoneyInput {
  amount_minor: number;
  currency?: string;
}

interface LineItemInput {
  description: string;
  quantity: number;
  unit: string;
  unit_price: MoneyInput;
  line_total: MoneyInput;
}

export interface CreateProposalInput {
  quote_id: string;
  template_id: string;
  branding: {
    company_name: string;
    logo_path?: string | null;
    primary_color?: string;
    phone?: string | null;
    email?: string | null;
    website?: string | null;
  };
  customer: {
    display_name: string;
    email?: string | null;
    phone?: string | null;
    property_address?: string | null;
  };
  line_items: LineItemInput[];
  subtotal_minor: number;
  tax_minor: number;
  total_minor: number;
  currency: string;
  scope_of_work: string;
  warranty_text?: string | null;
  terms_text?: string | null;
  valid_until?: string | null;
  qr_payload_url?: string | null;
}

/** Maps the web's human-readable input shape to the wire DTO the backend expects. */
function toCreatePayload(input: CreateProposalInput) {
  return {
    quote_id: input.quote_id,
    template_id: input.template_id,
    branding: input.branding,
    customer: input.customer,
    line_items: input.line_items,
    subtotal: { amount_minor: input.subtotal_minor, currency: input.currency },
    tax: { amount_minor: input.tax_minor, currency: input.currency },
    total: { amount_minor: input.total_minor, currency: input.currency },
    scope_of_work: input.scope_of_work,
    warranty_text: input.warranty_text ?? null,
    terms_text: input.terms_text ?? null,
    valid_until: input.valid_until ?? null,
    qr_payload_url: input.qr_payload_url ?? null,
  };
}

export function createProposal(token: string, input: CreateProposalInput): Promise<Proposal> {
  return apiFetch<Proposal>("/v1/proposals", {
    method: "POST",
    token,
    body: toCreatePayload(input),
  });
}

export function listProposals(token: string, quoteId?: string): Promise<Proposal[]> {
  const qs = quoteId ? `?quote_id=${quoteId}` : "";
  return apiFetch<Proposal[]>(`/v1/proposals${qs}`, { token });
}

export function getProposal(token: string, proposalId: string): Promise<Proposal> {
  return apiFetch<Proposal>(`/v1/proposals/${proposalId}`, { token });
}

export function sendProposal(token: string, proposalId: string, channel = "email"): Promise<Proposal> {
  return apiFetch<Proposal>(`/v1/proposals/${proposalId}/send`, {
    method: "POST",
    token,
    body: { channel },
  });
}

/** Maps a proposal status to a Badge variant — pure, unit-tested. */
export function statusBadgeVariantForProposal(
  status: Proposal["status"],
): "default" | "warning" {
  return status === "draft" ? "warning" : "default";
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- proposals.test.ts proposal-templates.test.ts`
Expected: `11 passed` (7 in `proposals.test.ts`, 4 in `proposal-templates.test.ts`)

- [ ] **Step 6: Run the full web suite and typecheck**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: all pass, zero type errors

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/proposals.ts apps/web/src/lib/proposals.test.ts apps/web/src/lib/proposal-templates.ts apps/web/src/lib/proposal-templates.test.ts
git commit -m "feat(T203): add proposals + proposal-templates web data layer"
```

---

### Task 10: Web pages — proposal list/detail, "Create Proposal" button, Settings template CRUD

**Files:**
- Create: `apps/web/src/app/(app)/proposals/page.tsx`
- Create: `apps/web/src/app/(app)/proposals/[id]/page.tsx`
- Modify: `apps/web/src/app/(app)/quotes/[id]/page.tsx`
- Modify: `apps/web/src/app/(app)/settings/page.tsx`

**Interfaces:**
- Consumes: everything from Task 9 (`proposals.ts`, `proposal-templates.ts`); `useAuthGuard()`;
  `formatMoney`; `Card`/`Badge`/`Button` UI components

This task, like T206's Task 6, adds no new unit tests of its own — Task 9 covers the logic it
composes, and this repo has no component-test infrastructure (vitest is `.ts`-only, no jsdom/RTL).
Verification is typecheck + build + a manual browser pass in Task 11.

- [ ] **Step 1: Proposals list page**

```tsx
// apps/web/src/app/(app)/proposals/page.tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { listProposals, statusBadgeVariantForProposal } from "@/lib/proposals";

export default function ProposalsPage() {
  const token = useAuthGuard();

  const {
    data: proposals,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["proposals"],
    queryFn: () => listProposals(token as string),
    enabled: !!token,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Proposals</h1>
        <p className="text-muted-foreground">Every branded proposal you&apos;ve sent, at every stage.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Proposals</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading proposals…</p>}
          {isError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t load proposals. Is the API Gateway running?
            </p>
          )}
          {proposals && proposals.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No proposals yet. Create one from a quote to get started.
            </p>
          )}
          {proposals && proposals.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Number</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 font-medium">Sent</th>
                    <th className="py-2 pr-4 font-medium">Viewed</th>
                  </tr>
                </thead>
                <tbody>
                  {proposals.map((proposal) => (
                    <tr key={proposal.id} className="border-b last:border-0 hover:bg-accent/50">
                      <td className="py-3 pr-4">
                        <Link href={`/proposals/${proposal.id}`} className="font-medium hover:underline">
                          {proposal.number}
                        </Link>
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant={statusBadgeVariantForProposal(proposal.status)} className="capitalize">
                          {proposal.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4">{proposal.sent_at ? new Date(proposal.sent_at).toLocaleDateString() : "—"}</td>
                      <td className="py-3 pr-4">{proposal.viewed_at ? new Date(proposal.viewed_at).toLocaleDateString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Proposal detail page**

```tsx
// apps/web/src/app/(app)/proposals/[id]/page.tsx
"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { getProposal, sendProposal, statusBadgeVariantForProposal } from "@/lib/proposals";
import { config } from "@/config";

export default function ProposalDetailPage() {
  const token = useAuthGuard();
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const {
    data: proposal,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["proposals", params.id],
    queryFn: () => getProposal(token as string, params.id),
    enabled: !!token,
  });

  const sendMutation = useMutation({
    mutationFn: () => sendProposal(token as string, params.id, "email"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", params.id] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
    },
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading proposal…</p>;
  if (isError || !proposal) {
    return (
      <p className="text-sm text-destructive">
        Couldn&apos;t load this proposal. Is the API Gateway running?
      </p>
    );
  }

  const viewUrl = `${config.apiUrl}/v1/proposals/${proposal.id}/view`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{proposal.number}</h1>
          <Badge variant={statusBadgeVariantForProposal(proposal.status)} className="mt-1 capitalize">
            {proposal.status}
          </Badge>
        </div>
        {proposal.status === "draft" && (
          <Button onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
            {sendMutation.isPending ? "Sending…" : "Send"}
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Document</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>Version {proposal.current_version}</p>
          <p>
            <a href={viewUrl} target="_blank" rel="noreferrer" className="text-primary hover:underline">
              View / download PDF
            </a>{" "}
            <span className="text-muted-foreground">— this is the same link the customer receives.</span>
          </p>
          {proposal.sent_at && <p className="text-muted-foreground">Sent {new Date(proposal.sent_at).toLocaleString()}</p>}
          {proposal.viewed_at && <p className="text-muted-foreground">Viewed {new Date(proposal.viewed_at).toLocaleString()}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Add "Create Proposal" to the quote detail page**

Read `apps/web/src/app/(app)/quotes/[id]/page.tsx` first to find its existing action-button layout
(where "Send"/"Accept"/"Reject" already live) and add a "Create Proposal" button alongside them that
navigates to `/proposals/new?quote_id=${quote.id}` — a lightweight creation page is out of this
plan's explicit code (the spec's own §6 describes the flow but a full template-picker form was not
separately speced with exact fields); implement it as a client component that: fetches
`listTemplates(token)`, lets the user pick one (defaulting to whichever has `is_default: true`),
and on submit calls `createProposal` with the quote's already-loaded line items/totals/customer
mapped into `CreateProposalInput`, then routes to `/proposals/{new.id}`. Follow the exact
`useAuthGuard` + `useMutation` pattern already used elsewhere in this codebase (e.g. the send/accept
buttons on this same quote detail page).

- [ ] **Step 4: Replace the Settings placeholder with template management**

Replace `apps/web/src/app/(app)/settings/page.tsx`'s branding-related placeholder text with a real
list of templates (`listTemplates`) plus a simple create form (`createTemplate`) — company name,
primary color (a plain `<input type="color">` or hex text input), default terms/warranty textareas,
and an `is_default` checkbox. Follow the `quotes/new/page.tsx` form pattern already established in
this codebase (react-hook-form + zod) for validation.

- [ ] **Step 5: Typecheck and build**

Run: `cd apps/web && pnpm typecheck && pnpm build`
Expected: zero type errors; `next build` produces all routes including `/proposals`,
`/proposals/[id]`, and `/proposals/new` with zero errors

- [ ] **Step 6: Commit**

```bash
git add "apps/web/src/app/(app)/proposals" "apps/web/src/app/(app)/quotes/[id]/page.tsx" "apps/web/src/app/(app)/settings/page.tsx"
git commit -m "feat(T203): add proposal list/detail pages, quote-to-proposal flow, template settings UI"
```

---

### Task 11: Full gate, live verification, tracker bookkeeping

**Files:**
- Modify: `TASKS.md`
- Modify: `tracking/PROGRESS-TRACKER.csv`

- [ ] **Step 1: Run every gate**

```bash
cd services/proposal-service && uv run ruff check app tests && uv run mypy app && uv run pytest -v
cd "/d/TradeQuote AI" && python scripts/check_conventions.py
cd apps/api-gateway && pnpm typecheck && pnpm test
cd packages/types && pnpm typecheck && pnpm build
cd apps/web && pnpm typecheck && pnpm test && pnpm build
```

Expected: every command exits 0.

- [ ] **Step 2: Live browser verification**

Start the API Gateway and `proposal-service`; log in on the web app; open a quote; click "Create
Proposal"; pick a template; submit. Confirm:

- The new proposal's detail page loads with status `draft` and a working "View / download PDF" link
- Clicking "Send" transitions status to `sent`
- Opening the "View / download PDF" link **in a fresh, unauthenticated browser context** (e.g. an
  incognito window with no login) still renders the PDF, and the proposal's status flips to `viewed`
  on refreshing the detail page — this is the one thing that cannot be verified by any unit test in
  this plan, since it depends on the real gateway's public-path routing (Task 1) actually working
  end-to-end, not just in Fastify's in-process `inject()` tests
- With the gateway stopped, `/proposals` and `/proposals/[id]` show the same honest error-banner
  treatment already established by `quotes`/`dashboard` (per this repo's established convention:
  never a silently stuck loading state)

If Postgres is unavailable in this environment (as it was for T206 — no Docker daemon, nothing on
`:5432`), record that explicitly rather than skipping the note: the happy path (real proposal
creation against live Postgres, and the `SECURITY DEFINER` `resolve_proposal_tenant` function
specifically) is **untestable without it**, exactly like T206's summary endpoint and the pre-existing
enum bug T206b tracks. Do not claim it was verified if it wasn't.

- [ ] **Step 3: Update `TASKS.md`**

Re-read the file first — do not assume the line numbers or exact prose below are still current;
another session may have edited `TASKS.md` in the meantime (this happened during T206). Find the
current `T203` line and:

- Change `- [ ]` to `- [x]`
- Replace the line's trailing text with a completed summary stating: the endpoints built
  (`/v1/proposal-templates`, `/v1/proposals` CRUD/send/view), the measured test counts from Step 1,
  that the public `/view` route required two gateway fixes (link to this plan's Task 1), and links to
  both [docs/modules/M8-proposal-builder.md](docs/modules/M8-proposal-builder.md) and
  [docs/modules/M8-proposal-builder-plan.md](docs/modules/M8-proposal-builder-plan.md)
- Remove `T203` from the "Check for Next Task" ready table
- Recompute the Module Completion Rollup: Phase 2's total is currently 8 (after `T206b`) — mark one
  more done. Recompute the Phase 2 percentage and the Total row precisely from the actual checkbox
  count at the time you make this edit, the same way the `T206b` ticket's rollup fix was done —
  do not copy stale numbers from this plan, which was written before `T203` started.
- Note in the "honest gaps" blockquote that `resolve_proposal_tenant` (the `SECURITY DEFINER`
  function backing the public view link) joins the existing "never run against live Postgres" gap —
  do not invent a new gap number scheme; fold it into the existing gap (1) language, matching how
  T206's summary endpoint was folded in.

- [ ] **Step 4: Update `tracking/PROGRESS-TRACKER.csv`**

Re-read the live `T203` row first (same reason as Step 3). Change `NOT_STARTED` → `DONE`, fill Start
Date and End Date with the actual date this task completes, and write a Notes cell describing the
finished work with your measured test counts — following the exact style of the `T206` row already
in this file (one long quoted string, semicolon-separated Quality Gates).

- [ ] **Step 5: Commit**

```bash
git add TASKS.md tracking/PROGRESS-TRACKER.csv
git commit -m "docs(T203): mark M8 Proposal Builder done, refresh rollup and tracker"
```

- [ ] **Step 6: Note for Agent 1 sign-off**

Per `AGENTS.md`'s cross-agent audit rule, flag this branch for CTO review before merge, calling out
explicitly: (a) the `packages/types` addition (Task 8), (b) the two gateway fixes (Task 1) — a
pre-existing binary-corruption bug fixed as a byproduct of this task, and a new pattern-matched
public-path mechanism whose blast radius is worth an extra look, and (c) the `SECURITY DEFINER`
Postgres function (Task 2), which is new attack-surface-adjacent SQL that deserves scrutiny even
though it's narrowly scoped to one read.

---

## Self-Review Notes

**Spec coverage:** D1 (proposal_template table) → Task 2/4/5. D2 (web orchestrates, full payload) →
Task 9/10's `createProposal`/`CreateProposalInput` shape matching Task 7's `ProposalCreate`. D3
(draft/sent/viewed only) → Task 3's `ProposalStatus`. D4 (public `/view`) → Tasks 1, 2, 3, 7 (the
resolver seam), 10 (the raw link), 11 (the one thing only a live browser pass can prove). D5
(`quote_id` no FK) → Task 2's migration. D6 (`packages/types`, flagged for audit) → Task 8, and
Task 11 Step 6 names it explicitly for the CTO. §3's enum caution → Task 4's `values_callable`, with
Task 3's `test_proposal_status_values_are_lowercase` as a direct regression guard. §7 error handling
→ Task 5 (template 404, DB-level default-uniqueness), Task 7 (`/view` 404, no tenant leakage). §8
testing strategy → Tasks 3–7, 9's unit tests plus Task 11's live pass. §9 out-of-scope (no
edit/regenerate path) → Task 6 deliberately has no `update_proposal`/re-render function. §10 DoD →
Task 11.

**Two things beyond the spec, resolved during planning, not silently smuggled in:** the gateway's
exact-match public-path allowlist and its `.text()` binary corruption (Task 1) — both load-bearing
prerequisites the spec's D4 assumed would just work. Flagged, fixed, tested, and called out again in
Task 11 Step 6 for audit.

**Placeholder scan:** no TBD/TODO beyond the one pre-existing `TODO(outbox)` comment carried over
verbatim from T107's own code (not new to this plan) and explicitly marked `TODO(outbox)` again in
Task 7's route so it stays consistent with the existing convention. Every step has complete code or
an exact command with expected output. Task 10 Steps 3–4 are the plan's least prescriptive steps
(no full line-by-line code for the "Create Proposal" mini-form or the Settings CRUD UI) — this is a
deliberate, disclosed scope choice, not an oversight: T206's plan gave full code for every UI change
because each was a single well-defined component; T203's two remaining UI pieces are genuinely
open-ended forms whose exact field layout wasn't specified in the approved spec (spec §6 describes
the flow, not pixel-level form fields). Rather than invent unapproved UI copy and layout wholesale,
these two steps specify the exact data flow, the exact functions to call, and the existing pattern to
follow, and leave layout judgment to whoever implements it — consistent with "follow established
patterns" rather than a placeholder.

**Type consistency:** `ProposalStatus` (Task 3) is consumed unchanged by Task 4's ORM mapping, Task
6's use cases, and Task 9's TS `Proposal["status"]` union (`"draft" | "sent" | "viewed"`, matching
the Python enum's three values exactly). `TenantResolver.resolve(proposal_id) -> UUID | None` (Task
3) is implemented identically by `PostgresTenantResolver` (Task 2) and `FakeTenantResolver` (Task 4),
and consumed with the same signature in Task 7's route. `ProposalCreate` (Task 6 schema) field names
match `CreateProposalInput`'s `toCreatePayload()` output (Task 9) field-for-field. `get_proposal`
is defined as a public function (no leading underscore) in Task 6 from the start, since Task 7's
route needs to call it too — an earlier draft of this plan had Task 6 define it private and told
Task 7 to rename it via a prose instruction; that was corrected during self-review so every task's
code is directly transcribable with no follow-up edit required.
