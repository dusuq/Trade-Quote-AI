# Notification Service

- **Owner Agent:** Agent 4 — Opus + Sonnet 4.6
- **Bounded Context / Purpose:** Multi-channel messaging

## Responsibilities

- Email (SendGrid), SMS/WhatsApp (Twilio), push
- Quote/proposal delivery, reminders, expiration, follow-up automation
- Templating + delivery tracking

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
