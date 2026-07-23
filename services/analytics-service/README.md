# Analytics Service

- **Owner Agent:** Agent 3 — Gemini (Med)
- **Bounded Context / Purpose:** KPIs, dashboards, forecasting

## Responsibilities

- Conversion, close rate, avg ticket, revenue forecast
- Profit by job/trade, LTV, repeat customers, lead sources
- Read-model projections from domain events

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
