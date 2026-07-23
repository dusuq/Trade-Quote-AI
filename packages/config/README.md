# Shared Config

- **Owner Agent:** Agent 1 — Opus 4.8
- **Bounded Context / Purpose:** Lint, tsconfig, env schema, constants

## Responsibilities

- ESLint/Prettier/tsconfig base, env validation (zod)

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
