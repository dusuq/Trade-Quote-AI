# API Gateway / BFF

- **Owner Agent:** Agent 1 — Opus 4.8
- **Bounded Context / Purpose:** Single secure entry point; routing, auth, rate limiting, aggregation

## Responsibilities

- JWT validation + RBAC + rate limiting\n- REST/gRPC routing to services\n- Mobile aggregation (BFF), public API surface

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
