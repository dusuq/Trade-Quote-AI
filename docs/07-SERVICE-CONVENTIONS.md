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

- **Prefer the Repository Pattern:** use cases depend on repository `Protocol`s (see
  `customer-service` — the gold-standard reference) so business logic is testable against in-memory
  fakes with no database.
- **Acceptable alternative:** injecting a `Session` directly into use cases (as `auth-service` and
  `quote-service` do today) **provided** every query is tenant-scoped _and_ the logic is covered by
  tests (DB-backed or SQLite is fine).
- **Not acceptable:** business logic that cannot be exercised without a live external Postgres, or a
  use case that reaches past its layer (e.g. a route running raw SQL).
- New services **should** default to the Protocol style; migrating the two `Session`-style services
  to it is tracked debt, not an emergency.

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
- **Include the FastAPI bugbear exemption in every service's `[tool.ruff.lint.flake8-bugbear]`**
  (`extend-immutable-calls` for `Depends`/`Query`/`Path`/`Body`/`Header`/`Cookie`/`Form`/`File`) —
  copy it from `services/pricebook-service/pyproject.toml`. Without it, ruff's B008 rule
  inconsistently flags the idiomatic `param: T = Query(...)` DI pattern depending on subtle
  signature details; this was found and fixed once already (T207 audit) — start new services with
  it in place rather than rediscovering it.
- **Test business logic against fakes** (no DB needed); integration tests that need Postgres run once
  the dev stack is verified (T002b).
- Target ≥80% coverage on domain/application logic.

## 8. Service HTTP surface

- Mount routes under `/v1/<plural-noun>` (e.g. `/v1/customers`, `/v1/pricebook`). Expose `/health`.
- Add the service to the gateway (`apps/api-gateway/src/config.ts` + `server.ts`,
  `registerServiceProxy`) so it's reachable — this is part of "done", not a follow-up.

## 9. Observability (T309b)

- Every service calls `instrument(app, ...)` from `app/infrastructure/observability.py`
  immediately after constructing `app = FastAPI(...)`, before routers are included. This
  is a **ported, not imported** file (no shared Python runtime package exists — same
  precedent as `integration-service`'s `http.py`) — copy it verbatim into a new service
  rather than reinventing it.
- Every piece is opt-in: `/metrics` is always mounted (Prometheus scraping needs no
  external endpoint), OpenTelemetry tracing only starts if `OTEL_EXPORTER_OTLP_ENDPOINT`
  is set, Sentry only initializes if `SENTRY_DSN` is set. A new service with neither
  configured must boot identically to one with T309b never applied.
- Add `sentry_dsn: str = ""` and `otel_exporter_otlp_endpoint: str = ""` to the service's
  `Settings`, and add the service's unit name (matching `infra/services.yml`) as
  `service_name` in the `instrument()` call — not the human-readable `app_name`, so
  telemetry lines up with the deploy topology and Prometheus target labels.
- Add the new unit to `infra/services.yml`; `scripts/gen_infra.py` generates its
  `app-metrics-{local,fly}.json` scrape targets automatically.

## 10. Security signal (T310b)

Distinct from section 9, and the distinction matters: those metrics answer _"is the
traffic healthy"_, these answer _"is someone attacking it"_. A platform can serve zero
5xx while a credential-stuffing run is in progress.

- **Do not add security counters to a domain service by default.** They live where the
  signal actually exists: the gateway (which sees the untrusted request _and_ the
  verified claims) and auth-service (which checks credentials). A domain service sees an
  already-validated `x-tenant-id` and has nothing to compare it against — a counter
  there would measure nothing. See [M27](modules/M27-security-observability.md).
- **Any label on a security counter must come from a closed set defined in code.** These
  counters are driven by _unauthenticated_ traffic, so a label derived from request input
  (a tenant id, a path segment, an email) is a remote "make Prometheus allocate a new
  time series" primitive. Route labels use the Fastify/FastAPI route **pattern**, never
  the concrete URL.
- **An auth endpoint must not reveal _why_ it failed.** Record the reason in metrics and
  in the tenant's audit log; return a flat message. Distinguishing "no such user" from
  "wrong password" turns the endpoint into an account-enumeration oracle. Enforced by
  `tests/security/test_security_invariants.py`.
- **Privileged actions go to `auth_audit_log`** via
  `services/auth-service/app/application/audit.py`. Successes join the caller's
  transaction; **failures need `record_isolated()`**, because a failing transaction rolls
  its own audit row back — losing exactly the rows anyone investigates. The table is
  append-only for `tradequote_app` (migration 0016); any future audit-style table must
  repeat that `REVOKE` explicitly.
- **Observe before you defend.** Where a handler strips or rejects something hostile,
  count it _first_ — after the strip there is nothing left to observe, and a silently
  refused attack is indistinguishable from no attack at all.

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
