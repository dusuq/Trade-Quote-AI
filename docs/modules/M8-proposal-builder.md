# T203 — M8 Proposal Builder · Design Spec

| Field            | Value                                                                       |
| ---------------- | --------------------------------------------------------------------------- |
| **Task**         | `T203`                                                                      |
| **Module**       | M8 — Proposal Builder                                                       |
| **Owner agent**  | Agent 2 (Sonnet 5 / Opus 5)                                                 |
| **Phase**        | Phase 2 — AI + Delivery                                                     |
| **Dependencies** | `T107` PDF engine ✅                                                        |
| **Date**         | 2026-07-26                                                                  |
| **Status**       | Design approved — ready for implementation planning                         |
| **Bounded ctx**  | `services/proposal-service` (extends T107, doesn't replace it) + `apps/web` |

---

## 1. Problem

`services/proposal-service` currently holds only T107's PDF engine: a **stateless** rendering
capability. `POST /v1/proposals/pdf` takes a fully-populated document in the request body, renders
it, stores the PDF, and returns a key — there is no `proposal` DB table, no templates, no
versioning, and no delivery/view tracking. T107's own README states this explicitly: it is
"deliberately narrower than the full Proposal Builder (M8/T203)... T203 will own persistence,
templates, and versioning, and will call into this engine rather than duplicate PDF logic."

Two things needed for a real Proposal Builder don't exist anywhere in the codebase yet:

1. **Company branding storage.** No table, column, or config carries a tenant's company name,
   logo, brand color, or default terms/warranty text. The web app's Settings page is a placeholder
   whose own copy says "Company profile + branding settings feed the PDF engine (T107) once wired
   up" — nothing backs that today.
2. **A customer-facing, unauthenticated view.** Every existing route in this codebase requires the
   gateway's `x-tenant-id`/`x-user-id` headers (a JWT-backed session). A customer opening a proposal
   link has no TradeQuote AI login.

`docs/06-DATABASE-SCHEMA.md` already earmarks a `proposal` table landing "when that module starts."

## 2. Decisions

### D1 — Branding + reusable content lives in a new `proposal_template` table, owned entirely by `proposal-service`

A tenant creates one or more named templates (e.g. "Standard") holding company name, logo URL,
primary color, and default terms/warranty text.

**Rejected alternatives:**

- _No persistence, pass branding fresh each call_ — matches T107's current behavior exactly, but
  there is no source for branding data anywhere, so proposals would never actually carry real
  branding. Zero new schema, but doesn't solve the actual problem.
- _Extend `auth-service`'s `tenant` table_ — architecturally arguable (branding is a company
  attribute, not a proposal attribute), but edits Agent 1's M1 schema and crosses agent ownership
  boundaries. AGENTS.md's coordination rule routes shared-contract changes through Agent 1 first;
  this table is heavier than what T203 alone needs.

**Why D1 wins:** stays entirely within `proposal-service`'s own bounded context — Agent 2's call
end-to-end, zero cross-agent coordination — and matches this repo's existing pattern where each
service owns its domain's data (quote-service owns quote data, pricebook-service owns pricing).

### D2 — The web app orchestrates; `proposal-service` never calls another service

`POST /v1/proposals` receives a fully-assembled document (`quote_id`, `template_id`, customer info,
line items, totals, terms/warranty overrides) from the web app, which already has the quote (via
`getQuote`) and customer data on hand from the quote-builder flow.

**Rejected alternative:** `proposal-service` fetches the quote and customer itself via HTTP given
just `{quote_id, template_id}`. Cleaner API surface, but this codebase has **zero** existing
synchronous service-to-service HTTP calls — no shared client, no established retry/timeout pattern,
no precedent for partial-failure handling. Introducing that machinery for T203 alone is out of
proportion to the task.

**Why D2 wins:** matches T107's existing endpoint shape exactly (already expects a fully-populated
body) and every other feature in this codebase (the quote builder UI already orchestrates multiple
gateway calls client-side).

### D3 — Proposal status is `draft → sent → viewed` only; signing is explicitly T204's job

**Rejected alternative:** mirror quote-service's full lifecycle now, including `accepted`/`rejected`,
even though no real signature backs it yet. Risk: T203 would define what "accepted" means for a
proposal before T204 — whose entire stated job is e-signature + audit trail (IP, timestamp, hash
chain) — has weighed in, inviting rework.

**Why D3 wins:** `T204`'s dependency on `T203` exists for a reason. Keeping the status enum to
generation/delivery/open-tracking keeps T203 tightly scoped to "generate and deliver a branded
document," and `T204` adds `accepted`/`signed` backed by real cryptographic signing rather than
retrofitting it.

### D4 — "Viewed" tracking requires one new, narrowly-scoped **public** endpoint

`GET /v1/proposals/{id}/view` — no `x-tenant-id` required, resolves the tenant from the proposal ID
itself, serves the PDF inline, flips `sent → viewed` on first hit only. This is the first
unauthenticated route in the codebase, so it's called out as its own decision rather than folded
quietly into D3. `ProposalDocument.qr_payload_url` (already present since T107) explicitly
anticipated "a future view/pay page" — this is that page, minus the "pay" part (T303's job).

### D5 — `quote_id` on `proposal` is a logical reference, not a DB foreign key

`quote` lives in `quote-service`'s own database. Consistent with how `quote.customer_id` already
works (customer-service's data, no cross-database FK). A direct consequence of D2: since
`proposal-service` never calls `quote-service`, it cannot validate that `quote_id` refers to a real
quote — it trusts the caller, the same way `quote.customer_id` already does.

### D6 — Two new domain events land in `packages/types`, flagged for CTO audit

`proposal.document.sent` and `proposal.document.viewed`, following the exact existing pattern
(`proposal.document.generated`/`.pdfRendered` are already registered; `esign.document.signed` is
already registered and waiting for T204). Per AGENTS.md, shared-package changes normally route
through Agent 1 — this spec adds two new event shapes (purely additive, nothing existing changes),
and flags the change explicitly for audit rather than treating it as routine.

## 3. Data model

Migration `infra/db/migrations/0006_proposal.sql` (next in sequence after `0005_quote.sql`):

```sql
CREATE TABLE proposal_template (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenant(id),
  name                text NOT NULL,
  company_name        text NOT NULL,
  logo_url            text,
  primary_color       text NOT NULL DEFAULT '#111827',
  phone               text,
  email               text,
  website             text,
  default_terms_text     text,
  default_warranty_text  text,
  is_default          boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
-- only one default template per tenant, enforced at the DB level, not just in application code
CREATE UNIQUE INDEX proposal_template_one_default_per_tenant
  ON proposal_template (tenant_id) WHERE is_default;

CREATE TYPE proposal_status AS ENUM ('draft', 'sent', 'viewed');

CREATE TABLE proposal (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  quote_id          uuid NOT NULL,   -- logical reference only; quote lives in quote-service (D5)
  template_id       uuid NOT NULL REFERENCES proposal_template(id),
  number            text NOT NULL,   -- "P-2026-000001", same scheme as quote.number
  status            proposal_status NOT NULL DEFAULT 'draft',
  current_version   int NOT NULL DEFAULT 1,
  storage_key       text,            -- latest rendered PDF's key in PdfStorage
  sent_at           timestamptz,
  viewed_at         timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, number)
);

CREATE TABLE proposal_version (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  proposal_id   uuid NOT NULL REFERENCES proposal(id) ON DELETE CASCADE,
  version       int NOT NULL,
  snapshot      jsonb NOT NULL,   -- full ProposalDocument at render time
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (proposal_id, version)
);
```

**Scope of "versioning" in T203, made explicit:** creation writes exactly one `proposal_version`
row (`version = 1`), captured at render time. There is no edit/regenerate endpoint in this spec, so
`current_version` never advances past 1 within T203 — the table exists so a later task can append
`version = 2+` without a schema change, not because T203 itself builds the increment path. See §9.

`proposal` and `proposal_version` carry RLS on `tenant_id`, same as every other tenant-scoped table
(conventions §2). `proposal_template` is likewise tenant-scoped and RLS-protected.

**Enum caution (carried forward from `T206b`):** SQLAlchemy's `Enum(...)` mapping must declare
`values_callable=lambda e: [m.value for m in e]` for `proposal_status`, or it will persist the
Python member's `.name` (`'DRAFT'`) against a Postgres type declaring lowercase labels (`'draft'`)
— exactly the bug `T206b` exists to fix service-wide. Get this right from the start here rather than
adding a fourth instance of it.

## 4. API surface

New route modules split out from the (currently T107-only) `interface/routes.py`:

```
app/interface/
├── routes.py           EDIT — becomes a thin router-of-routers
├── template_routes.py  NEW — /v1/proposal-templates
├── proposal_routes.py  NEW — /v1/proposals (adds to, doesn't replace, T107's existing /pdf routes)
└── schemas.py          EDIT — + template & proposal DTOs
```

| Method | Path                          | Auth                | Purpose                                                                                                                                                 |
| ------ | ----------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/v1/proposal-templates`      | tenant              | Create a template                                                                                                                                       |
| GET    | `/v1/proposal-templates`      | tenant              | List tenant's templates                                                                                                                                 |
| PUT    | `/v1/proposal-templates/{id}` | tenant              | Update a template                                                                                                                                       |
| POST   | `/v1/proposals`               | tenant              | Create from `{quote_id, template_id, customer, line_items, subtotal, tax, total, warranty_text?, terms_text?}` — renders v1 immediately, status `draft` |
| GET    | `/v1/proposals`               | tenant              | List (filter by `quote_id`, `status`)                                                                                                                   |
| GET    | `/v1/proposals/{id}`          | tenant              | Get one, with version history                                                                                                                           |
| POST   | `/v1/proposals/{id}/send`     | tenant              | `draft` → `sent`, stamps `sent_at`                                                                                                                      |
| GET    | `/v1/proposals/{id}/pdf`      | tenant              | (existing T107 route, unchanged) contractor's own authenticated fetch                                                                                   |
| GET    | `/v1/proposals/{id}/view`     | **public, no auth** | Customer's link: PDF inline, `sent`→`viewed` on first hit, stamps `viewed_at`                                                                           |

**Gateway:** two new prefixes to register in `apps/api-gateway/src/server.ts`/`config.ts` —
`/v1/proposal-templates` and (if not already covered by the existing `/v1/proposals` prefix
registration from T107) confirm `/v1/proposals/{id}/view` passes through unauthenticated; the
gateway's proxy must not itself require a bearer token on that specific path. One line each,
following the exact pattern already used for the other services.

**The public route's boundary, stated precisely:** `/v1/proposals/{id}/view` must never read or
require `x-tenant-id`. It resolves `tenant_id` from an unscoped lookup by `proposal_id` first, then
opens a `tenant_session` for that resolved tenant to read the rest. This is the one route in the
service that intentionally does not follow "the gateway already authenticated you."

## 5. Domain events

```typescript
// packages/types/src/events.ts
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

Registered as `"proposal.document.sent"` / `"proposal.document.viewed"` in `DomainEventPayloadMap`
and the `DomainEventName` union, alongside the existing `proposal.document.generated`/
`.pdfRendered`. Purely additive — no existing event shape changes.

`app/domain/events.py` gets matching factory functions `proposal_sent`/`proposal_viewed`, mirroring
`document_generated`/`pdf_rendered` already there. Events are returned from use cases and persisted
by the route layer in the same DB transaction as the status change — matching quote-service's
existing practice (no outbox table exists anywhere in this codebase yet; T203 doesn't invent one).

## 6. Web UI

```
apps/web/src/lib/proposals.ts                    NEW — types, form schema, API calls (mirrors quotes.ts)
apps/web/src/lib/proposal-templates.ts           NEW — template CRUD API calls
apps/web/src/app/(app)/proposals/page.tsx        NEW — list, same table pattern as quotes/page.tsx
apps/web/src/app/(app)/proposals/[id]/page.tsx   NEW — detail: status, version history, PDF download, "Send"
apps/web/src/app/(app)/quotes/[id]/page.tsx      EDIT — add a "Create Proposal" button
apps/web/src/app/(app)/settings/page.tsx         EDIT — replace the branding placeholder with real template CRUD
```

Flow: on a quote's detail page, "Create Proposal" opens a form (pick a template, optionally override
terms/warranty) → assembles the payload from the already-loaded `quote` + `customer` → `POST
/v1/proposals` → redirects to the new proposal's detail page (rendered PDF + "Send" action).

**The public view link needs no web page.** `GET /v1/proposals/{id}/view` returns the PDF directly
(`media_type: application/pdf`); a browser opening the gateway-routed URL renders it natively. No
separate branded landing page in this task — reasonable T205 (Notifications/delivery) territory.

The Settings page placeholder covers branding + team + tax rules + integrations; T203 only replaces
the branding/template slice.

## 7. Error handling & edge cases

| Condition                                  | Response                                                                          |
| ------------------------------------------ | --------------------------------------------------------------------------------- |
| `template_id` doesn't exist                | `404`                                                                             |
| `quote_id` doesn't exist in quote-service  | **Accepted silently** — never validated (D5); same as `quote.customer_id` today   |
| `GET /v1/proposals/{id}/view` unknown `id` | `404`, generic message (no tenant/existence leakage — public route)               |
| Second (or later) hit on `/view`           | Status stays `viewed`; `viewed_at` does **not** re-stamp on repeat views          |
| Two templates both set `is_default = true` | Rejected at the DB level via the partial unique index, not just application logic |

## 8. Testing strategy

Mirrors T107's existing style (fakes for use cases) plus T206's DB-backed pattern (SQLite harness):

- `template_services`: create/list/update; default-uniqueness constraint (DB-level, via a real
  integrity-error assertion, not just an application check)
- `proposal_services`: create → renders v1 + persists `proposal_version` row; send → status
  transition + `sent_at`; view → status transition + `viewed_at`, **and** a second view doesn't
  re-stamp `viewed_at` or regress status
- **Tenant isolation test** on every new tenant-scoped query (conventions §2, non-negotiable)
- Route test proving `GET /v1/proposals/{id}/view` succeeds with **no** `x-tenant-id` header — the
  inverse of every other route test in this codebase, and worth its own explicit assertion given
  it's new surface
- `Enum(proposal_status, values_callable=...)` — a) mapped correctly, b) a portable-SQL test doesn't
  catch the Postgres-label mismatch (SQLite degrades `Enum` to VARCHAR+CHECK, same blind spot T206b
  is fixing elsewhere), so this needs an explicit round-trip test asserting the persisted value is
  lowercase, not the Python member name
- Web: `proposals.ts`/`proposal-templates.ts` unit tests mirroring `quotes.ts`'s existing style

## 9. Out of scope (deferred, not forgotten)

- **Editing a proposal after creation / regenerating a new version.** `current_version` stays at 1
  throughout T203; `proposal_version` exists so a future increment doesn't need a schema change,
  but no endpoint in this spec produces `version = 2+`. If terms/warranty need a correction before
  sending, today's answer is: create a new proposal.
- Actual email/SMS delivery of the view link — **T205**
- Signature capture, audit trail, hash chain — **T204**
- A branded public landing page around the raw PDF response — reasonable **T205** follow-up
- Payment collection — **T303**
- Full Settings page (team members, tax rules, integrations) — only the branding/template slice is
  in scope here

## 10. Definition of Done

- [ ] `infra/db/migrations/0006_proposal.sql` applied structurally valid; `proposal_status` enum
      uses `values_callable` correctly (see §3 caution)
- [ ] `proposal_template`, `proposal`, `proposal_version` — CRUD/lifecycle implemented per §4
- [ ] `GET /v1/proposals/{id}/view` works with no `x-tenant-id`, tested explicitly
- [ ] Two new domain events added to `packages/types`, flagged for CTO audit (D6)
- [ ] Web: proposal list/detail pages, "Create Proposal" on quote detail, template management in
      Settings
- [ ] Gateway routes `/v1/proposal-templates` and confirms `/v1/proposals/{id}/view` bypasses auth
- [ ] `ruff` · `mypy` · `pytest` · `check_conventions.py` · `pnpm typecheck` · `pnpm test` ·
      `next build` all clean
- [ ] Live browser verification, including the public view link with no session/token present
- [ ] `services/proposal-service/README.md` updated (currently describes T107 only)
- [ ] `TASKS.md` `T203` checked; `tracking/PROGRESS-TRACKER.csv` row set to `DONE`
- [ ] Agent 1 (CTO) sign-off, with explicit attention to D6 (the `packages/types` change) and the
      new public-route boundary (D4)

## 11. Risks

| Risk                                                                       | Mitigation                                                                    |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Public `/view` route accidentally trusts `x-tenant-id` if present          | Route explicitly ignores that header; test asserts success with it absent     |
| `proposal_status` enum hits the same Postgres-label bug as T206b           | `values_callable` set correctly from the start; explicit round-trip test (§8) |
| Two default templates race past an application-only check                  | DB-level partial unique index, not application logic alone (§3)               |
| `quote_id` referencing a nonexistent or wrong-tenant quote goes undetected | Accepted limitation of D2/D5; documented, not hidden                          |
| `packages/types` change conflicts with a concurrent Agent 1 edit           | Purely additive (new interfaces + union members only); flagged for audit (D6) |
