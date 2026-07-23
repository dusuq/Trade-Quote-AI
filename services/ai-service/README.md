# AI Service

- **Owner Agent:** Agent 1 (NLP/copilot) / Agent 3 (vision/OCR)
- **Bounded Context / Purpose:** All AI capabilities

## Responsibilities

- Voice→quote, scope/proposal writing, copilot Q&A\n- AI Vision (equipment detection), OCR (invoices/blueprints)\n- Sales coach, pricing optimization, AI usage metering

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
