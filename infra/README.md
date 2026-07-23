# Infrastructure

- **Owner Agent:** Agent 4 — Opus + Sonnet 4.6
- **Bounded Context / Purpose:** Docker, K8s, Terraform, CI/CD

## Responsibilities

- Local Docker Compose (postgres/redis/minio/opensearch)\n- K8s manifests, Terraform IaC, GitHub Actions pipelines\n- Monitoring stack (Prometheus/Grafana/Loki/Sentry)

## Definition of Done

- Clean Architecture layering (domain → application → infrastructure → interface)
- Contract published/consumed via `packages/types` (OpenAPI/gRPC + domain events)
- Tenant-scoped (`tenant_id` + RLS) where data is persisted
- Tests: unit + integration (≥80% on domain logic)
- Passes the 12 Quality Gates → Agent 1 sign-off
- `TASKS.md` box checked + `tracking/PROGRESS-TRACKER.csv` row set to DONE
