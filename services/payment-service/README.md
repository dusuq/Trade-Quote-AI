# Payment Service

- **Owner Agent:** Agent 4 — Opus + Sonnet 4.6
- **Bounded Context / Purpose:** Payments, deposits, invoices

## Responsibilities

- Stripe/Square/PayPal/ACH, deposits, installments, partial
- Invoices, webhooks, idempotency
- PCI-safe (no card data stored)

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
