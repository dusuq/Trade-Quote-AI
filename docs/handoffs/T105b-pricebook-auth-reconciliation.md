# 🔀 Handoff — T105b · Reconcile pricebook-service to the gateway auth pattern

- **From:** Agent 1 (CTO)
- **To:** **Agent 3 — Google Antigravity (Gemini)** (owner of pricebook-service)
- **Depends on:** T105 (pricebook built, ✅) + the new `docs/07-SERVICE-CONVENTIONS.md`
- **Priority:** P0 — this is both an architecture-consistency fix and a real integration bug.

---

## Why

Your pricebook-service (T105) decodes JWTs itself (`app/interface/routes.py`,
`_extract_auth_context`). Per **`docs/07-SERVICE-CONVENTIONS.md` section 1**, only `auth-service`
may touch `jwt`; every other service trusts the API Gateway's `x-tenant-id` / `x-user-id` headers
(the gateway already verified the token). The reference implementation is `customer-service`.

This isn't only style — it's a **live bug**: your code reads the claim `payload["tenant_id"]`, but
the gateway issues tokens with the claim named **`tid`** (see `apps/api-gateway` / auth-service).
So as written, pricebook would reject every real gateway-authenticated request.

The convention is now enforced by CI (`scripts/check_conventions.py`) — the build is **red** until
this is fixed. The same guard also flags quote-service (T106), whose owner has the same fix to make.

## What to change (pricebook-service only — your file)

In `app/interface/routes.py`:

**Remove** `import jwt` and the whole `_extract_auth_context(...)` helper. **Replace** with header
trust, mirroring `services/customer-service/app/interface/routes.py`:

```python
from uuid import UUID
from fastapi import Header, HTTPException, status

def _require_tenant(x_tenant_id: str | None) -> UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc

def _require_user(x_user_id: str | None) -> UUID | None:
    if not x_user_id:
        return None
    try:
        return UUID(x_user_id)
    except ValueError:
        return None
```

Then update each route handler to take `x_tenant_id: str | None = Header(default=None)` (and
`x_user_id` where an actor is needed) instead of `authorization`, and call `_require_tenant(...)`.

Also remove the now-unused `jwt_secret_key` / `jwt_algorithm` from `app/config.py`.

## Acceptance criteria

1. `python scripts/check_conventions.py` → **OK** (no auth-boundary violation for pricebook).
2. `ruff check app tests` clean; `mypy app` clean; `pytest` green (update the tests that previously
   sent `Authorization` to send `x-tenant-id` instead).
3. No `import jwt` anywhere in pricebook-service.
4. Commit as `fix(T105b): reconcile pricebook-service to gateway auth pattern` and flip `T105b` →
   DONE in `TASKS.md` + `tracking/PROGRESS-TRACKER.csv`.

## On completion

Report back. **Agent 1 will audit** (T105c): re-run the guard + ruff/mypy/pytest, confirm no `jwt`
usage, and confirm the gateway→pricebook path uses headers end-to-end. Only then is T105 fully
signed off.
