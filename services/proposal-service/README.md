# Proposal Service (Builder + PDF + E-Sign)

- **Owner Agent:** Agent 2 (builder) / Agent 4 (PDF+sign)
- **Bounded Context / Purpose:** Proposal documents, PDF, signatures

## Responsibilities

- Templates, cover page, branding, warranty, terms\n- Branded PDF engine (QR, payment button, before/after photos)\n- E-signature + audit trail (IP, timestamp, hash chain)

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
