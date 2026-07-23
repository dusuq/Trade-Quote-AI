# Shared UI / Design System

- **Owner Agent:** Agent 2 — Sonnet 5
- **Bounded Context / Purpose:** Reusable components, tokens, themes

## Responsibilities

- Tailwind + shadcn/ui components, design tokens\n- Dark mode, accessibility primitives, white-label theming

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
