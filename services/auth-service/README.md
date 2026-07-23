# Auth Service

- **Owner Agent:** Agent 1 — Opus 4.8
- **Bounded Context / Purpose:** Identity, tenants, RBAC, sessions (Module M1)
- **Status:** T101 implemented + unit-verified (security core: 9/9 tests green, ruff clean). Live DB integration runs under **T002b**.

## Responsibilities

- Tenants, users, roles/permissions (RBAC), JWT access + rotating refresh tokens
- MFA (TOTP) enrollment/verification, password hashing (PBKDF2 → argon2 target)
- OAuth (Google/Microsoft), Clerk/Auth0 integration (planned)
- Auth audit log; emits `auth.tenant.created` / `auth.user.invited` domain events

## Architecture (Clean Architecture layering)

```
app/
├── domain/          entities.py (Tenant/User/RoleKey), events.py (auth.* events)
├── application/     security.py (pure: hash/JWT/TOTP), services.py (use cases)
├── infrastructure/  db.py (tenant-scoped Session → RLS), models.py (ORM)
└── interface/       schemas.py (Pydantic DTOs), routes.py (FastAPI)
main.py              FastAPI app + /health
```

Tables are defined in [`infra/db/migrations`](../../infra/db/migrations) (0002_auth_tenancy.sql) and
documented in [docs/06-DATABASE-SCHEMA.md](../../docs/06-DATABASE-SCHEMA.md). Multi-tenant isolation is
enforced by Postgres RLS; `tenant_session()` sets `app.current_tenant` per transaction.

## Endpoints (v1)

| Method | Path                | Purpose                              |
| ------ | ------------------- | ------------------------------------ |
| POST   | `/v1/auth/register` | Create tenant + owner, return tokens |
| POST   | `/v1/auth/login`    | Authenticate (+ MFA), return tokens  |
| GET    | `/v1/auth/me`       | Decode bearer token → current user   |
| GET    | `/health`           | Liveness                             |

## Develop

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest -q                     # unit tests (no DB needed for security core)
uvicorn app.main:app --reload --port 8001
```

## Definition of Done

- ✅ Clean Architecture layering (domain → application → infrastructure → interface)
- ✅ Emits domain events per `packages/types` contract
- ✅ Tenant-scoped (RLS via `app.current_tenant`)
- ✅ Unit tests on security core (9/9); ruff clean
- ⏳ Integration test against live Postgres — **pending T002b** (stack smoke test on GCP)
- ⬜ Full RBAC permission catalog seed + refresh/rotation endpoints (follow-up)
