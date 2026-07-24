# Customer Service (CRM)

- **Owner Agent:** Agent 2 — Sonnet 5 (T104 built by Agent 1/CTO to unblock the chain)
- **Bounded Context / Purpose:** Customers, contacts, properties, tags, notes, timeline (Module M4)
- **Status:** T104 implemented + verified (21/21 tests, ruff + mypy clean). Live DB integration under T002b.
- **Note:** Lead management (M5) is a separate later task (T-lead, Phase 2) in this same service.

## Responsibilities

- Customers: create, get, tenant-scoped search with pagination
- Contacts (with single-primary invariant), properties (with geo), tags (dedup per label), notes
- Customer timeline — chronological activity view (notes today; future services project their
  own domain events into the same shape)
- Emits `customer.customer.created` / `customer.property.added` per the `packages/types` contract

## Architecture (Clean Architecture + Repository Pattern)

```
app/
├── domain/          entities.py, repositories.py (Protocols/ports), events.py, errors.py
├── application/     services.py (use cases — depend only on repo Protocols), pagination.py (pure)
├── infrastructure/  db.py (tenant-scoped Session → RLS), models.py (ORM),
│                    sqlalchemy_repositories.py (concrete adapters)
└── interface/       schemas.py (Pydantic DTOs), routes.py (FastAPI)
main.py              FastAPI app + /health
```

The **Repository Pattern** is the key design choice: use cases in `application/services.py` depend
only on the `Protocol`s in `domain/repositories.py`, so the entire business logic is tested against
in-memory fakes (`tests/fakes.py`) — 21 tests, zero database, zero mocking framework. The
SQLAlchemy implementations satisfy the same Protocols and are swapped in at the HTTP layer.

Tables: `infra/db/migrations/0003_customer.sql`. Multi-tenant isolation via Postgres RLS;
`tenant_session()` sets `app.current_tenant` per transaction. This service **trusts the API
Gateway's** `x-tenant-id`/`x-user-id` headers (the gateway already verified the JWT) and never
decodes tokens itself.

## Endpoints (v1, mounted behind the gateway at `/v1/customers`)

| Method | Path                            | Purpose                                 |
| ------ | ------------------------------- | --------------------------------------- |
| POST   | `/v1/customers`                 | Create customer                         |
| GET    | `/v1/customers`                 | Search (query `q`, `page`, `page_size`) |
| GET    | `/v1/customers/{id}`            | Get one                                 |
| POST   | `/v1/customers/{id}/properties` | Add property                            |
| POST   | `/v1/customers/{id}/contacts`   | Add contact (primary demotes prior)     |
| POST   | `/v1/customers/{id}/notes`      | Add note                                |
| POST   | `/v1/customers/{id}/tags`       | Tag customer (reuses tag by label)      |
| GET    | `/v1/customers/{id}/timeline`   | Chronological activity                  |
| GET    | `/health`                       | Liveness                                |

## Develop

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest -q                     # 21 tests, no DB needed (fakes)
uvicorn app.main:app --reload --port 8002
```

## Definition of Done

- ✅ Clean Architecture + Repository Pattern; use cases depend only on Protocols
- ✅ Emits domain events per `packages/types` contract
- ✅ Tenant-scoped (RLS via `app.current_tenant`); tenant-isolation covered by tests
- ✅ 21 unit tests (create/get/search/pagination/property/contact-primary/note/tag/timeline +
  tenant-isolation), ruff + mypy clean
- ⏳ Integration test against live Postgres — **pending T002b**
- ⬜ Lead management (M5), photo attachments (object storage) — later tasks
