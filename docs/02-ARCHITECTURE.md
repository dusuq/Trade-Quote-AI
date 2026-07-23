# 02 — System Architecture

TradeQuote AI is an **event-driven, multi-tenant, API-first, cloud-native** platform built as a
monorepo of independently deployable bounded contexts. Every architectural choice preserves the
long-term evolution `Quote → … → AI Operating System for Trades` without major rewrites.

---

## High-Level Topology

```
        ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
        │   Web App    │   │ Flutter App  │   │  Public API  │
        │  (Next.js)   │   │(iOS/Android) │   │  / Zapier    │
        └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
               └──────────────────┼──────────────────┘
                          ┌───────▼────────┐
                          │  API Gateway    │  auth · rate-limit · routing
                          │   (BFF)         │
                          └───────┬────────┘
        ┌──────────┬──────────┬───┼────────┬──────────┬──────────┐
        ▼          ▼          ▼   ▼        ▼          ▼          ▼
     Auth      Customer    Quote  Pricebook Proposal   AI      Payment
    service    service    service service   service  service  service
        │          │          │      │        │          │        │
        └──────────┴──────────┴──────┴────────┴──────────┴────────┘
                          Domain Events (Event Bus: Redis Streams → Kafka at scale)
        ┌──────────────────────────────────────────────────────────┐
        ▼                    ▼                ▼              ▼
  Notification         Analytics       Integration     (future services)
    service             service          service
        │
   ┌────┴──────────────────────────────────────────────────────────┐
   ▼                ▼              ▼             ▼            ▼
 PostgreSQL       Redis      Object Store   OpenSearch   Vector DB
 (per-tenant     (cache/     (S3/MinIO)     (search)     (pgvector/
  schema)         queue)                                   Qdrant)
```

## Multi-Tenancy

- **Model:** shared database, **tenant-scoped rows** with a mandatory `tenant_id` on every table + Postgres Row-Level Security. Upgrade path to schema-per-tenant / DB-per-tenant for enterprise white-label.
- Every query, event, cache key, and storage prefix is tenant-scoped. No cross-tenant reads — ever.

## Event-Driven Contracts

- Services communicate **synchronously** via the gateway (REST/gRPC) and **asynchronously** via domain events.
- Event naming: `<context>.<aggregate>.<past-tense-verb>` e.g. `quote.estimate.accepted`, `proposal.document.signed`.
- Every event carries `{ eventId, tenantId, occurredAt, actorId, payload, version }`.
- Agent 1 owns the canonical event registry in `packages/types` — see **[03-DOMAIN-EVENTS.md](03-DOMAIN-EVENTS.md)** for the full registry, envelope, and delivery guarantees (transactional outbox, at-least-once, idempotent consumers).

## Per-Service Patterns

Clean Architecture layering inside each service: `domain/` (entities, value objects, events) →
`application/` (use cases, CQRS handlers) → `infrastructure/` (repos, adapters) → `interface/` (HTTP/gRPC).

## Offline-First (Mobile)

- Local SQLite (Drift) mirror of the working set; mutations queued and reconciled via the sync engine (M14).
- Conflict resolution: last-write-wins on scalar fields, merge on line-item collections, server-authoritative on money/tax.

## Cross-Cutting

- **Security:** JWT + RBAC at gateway, RLS at DB, secrets via env/manager, OWASP Top-10 baseline.
- **Observability:** OpenTelemetry traces across gateway→services→DB; Prometheus/Grafana metrics; Loki logs; Sentry errors.
- **Idempotency:** all money-moving and AI-billing endpoints require idempotency keys.

See ADRs in `docs/adr/` for individual decisions.
