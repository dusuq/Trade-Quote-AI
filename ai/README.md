# AI Assets

- **Owner Agent:** Agent 1 (prompts) / Agent 3 (eval)
- **Bounded Context / Purpose:** Prompts, agent defs, eval harness

## Responsibilities

- Versioned prompt library, agent role definitions
- Eval datasets + regression harness for AI features

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
