# Mobile App (Flutter)

- **Owner Agent:** Agent 4 — Opus + Sonnet 4.6
- **Bounded Context / Purpose:** iOS/Android/tablet field app, offline-first

## Responsibilities

- Camera, voice, GPS, biometrics, push, widgets\n- Local SQLite (Drift) + sync engine (M14)\n- One-handed UX, large touch targets, dark mode

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
