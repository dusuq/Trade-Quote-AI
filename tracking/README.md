# Progress Tracking

- **Owner Agent:** All agents (CTO curates)
- **Bounded Context / Purpose:** Live development status

## Responsibilities

- `PROGRESS-TRACKER.csv` → import to Google Sheets\n- Keep in sync with `TASKS.md` after every completed task

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
