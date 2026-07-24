# 07 — Service Conventions (The Golden Path)

**Every backend service MUST follow these conventions.** They are not style preferences — several are
enforced automatically by CI (`scripts/check_conventions.py`, run in the Python lane). A PR that
violates an enforced rule fails the build. This document is the single source of truth; when in
doubt, match `services/auth-service` and `services/customer-service` (the reference implementations).

> **Why this exists:** in a multi-agent fleet, un-codified patterns drift. The auth pattern below
> was implemented three different ways across three services before this doc + guard existed. Codify
> once, enforce in CI, never re-litigate.

---

## 1. Authentication & tenancy — the ONE pattern ✅ enforced

**The API Gateway is the only component that verifies JWTs.** It decodes the bearer token, then
forwards trusted identity headers to downstream services:

- `x-tenant-id` — the tenant UUID (services scope everything to this)
- `x-user-id` — the acting user UUID (nullable for system calls)
- `x-user-roles` — comma-separated roles
- `x-request-id` — trace correlation

**Downstream services MUST NOT decode JWTs.** They read `x-tenant-id`/`x-user-id` from headers and
trust them (the gateway already authenticated the request). A service that reaches for `import jwt`
is almost always doing it wrong.

- ✅ **Allowed to use `jwt`:** `services/auth-service` only — it _issues_ and _validates_ tokens; that
  is its bounded context.
- ❌ **Forbidden:** every other service. **CI fails** (`check_conventions.py`) if any non-auth service
  imports `jwt` or calls `jwt.decode`.

Reference: `services/customer-service/app/interface/routes.py` (`_require_tenant(x_tenant_id)`).

## 2. Multi-tenancy & RLS

- Every tenant-scoped table carries `tenant_id` and is protected by Postgres Row-Level Security.
- Open a DB session via the service's `tenant_session(tenant_id)` helper, which sets
  `app.current_tenant` so RLS filters every query. Never run tenant queries on a raw session.
- **Never cross tenants.** Tenant isolation must have an explicit unit test (see
  `customer-service` `test_enforces_tenant_isolation`).

## 3. Clean Architecture layering

```
app/
├── domain/          entities/value objects, repository Protocols, domain events, errors — no I/O
├── application/     use cases (pure orchestration), depend only on domain Protocols
├── infrastructure/  DB session, ORM models, concrete repository adapters
└── interface/       Pydantic DTOs, FastAPI routes (thin adapters)
main.py              FastAPI app + /health
```

- **Use cases depend on repository `Protocol`s, not on SQLAlchemy.** This is what makes business logic
  testable against in-memory fakes without a database (Repository Pattern). Reference:
  `customer-service`.

## 4. Domain events

- Mirror the canonical registry in `packages/types` (`docs/03-DOMAIN-EVENTS.md`). Never invent an
  event name or payload shape locally — if you need a new one, extend `packages/types` (Agent 1 owns
  breaking changes) first.
- Naming: `<context>.<aggregate>.<pastTenseVerb>`. Envelope fields are mandatory and uniform.

## 5. Money & rates

- Money is **integer minor units** (`*_minor: int`, cents) + an ISO-4217 currency. **Never floats.**
- Rates/margins are **basis points** (`*_bps: int`; 10000 = 100%).

## 6. Time ✅ enforced (via ruff UP017)

- Use `datetime.now(UTC)` — import `from datetime import UTC`. **Not** `datetime.now(timezone.utc)`
  (ruff `UP017` fails CI). Always timezone-aware UTC; serialize as ISO-8601.

## 7. Tooling & tests ✅ enforced

- Each service is a `uv`/Poetry project with a `pyproject.toml` declaring **`[tool.ruff]`** and
  **`[tool.mypy]`** (both required; CI checks their presence).
- `ruff check` and `mypy app` must be clean; `pytest` must pass. The CI Python lane runs all three
  per service automatically.
- **Test business logic against fakes** (no DB needed); integration tests that need Postgres run once
  the dev stack is verified (T002b).
- Target ≥80% coverage on domain/application logic.

## 8. Service HTTP surface

- Mount routes under `/v1/<plural-noun>` (e.g. `/v1/customers`, `/v1/pricebook`). Expose `/health`.
- Add the service to the gateway (`apps/api-gateway/src/config.ts` + `server.ts`,
  `registerServiceProxy`) so it's reachable — this is part of "done", not a follow-up.

---

## Enforcement summary

| Rule                                     | How it's enforced                               |
| ---------------------------------------- | ----------------------------------------------- |
| No JWT decode outside auth-service       | `scripts/check_conventions.py` (CI, hard fail)  |
| Each service declares ruff + mypy config | `scripts/check_conventions.py` (CI, hard fail)  |
| `datetime.now(UTC)` not `timezone.utc`   | ruff `UP017` (CI, hard fail)                    |
| ruff/mypy/pytest clean                   | CI Python lane, per service                     |
| Tenant isolation                         | required unit test (reviewed)                   |
| Clean Architecture / events / money      | code review against this doc (Agent 1 sign-off) |

If you believe a rule is wrong for a specific case, do **not** silently deviate — raise it with the
CTO (Agent 1), and if agreed, this doc + the guard change together in one PR.
