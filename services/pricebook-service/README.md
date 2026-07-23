# Pricebook Service

- **Owner Agent:** Agent 2 — Sonnet 5
- **Bounded Context / Purpose:** Material/labor/equipment catalog

## Responsibilities

- Materials, labor, equipment, consumables, rentals, packages
- Regional + supplier pricing, bulk import, search (OpenSearch)
- Auto-update hooks

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
