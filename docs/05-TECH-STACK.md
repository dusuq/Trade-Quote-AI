# 05 — Technology Stack & Rationale

| Layer            | Choice                                                                                                                   | Why                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| Web frontend     | Next.js · React · TypeScript · Tailwind · shadcn/ui · Radix · TanStack Query · Zustand · React Hook Form · Framer Motion | Fast, mobile-first, accessible, SSR/edge-ready, huge ecosystem                    |
| Mobile           | Flutter (Dart) · Drift (SQLite) · Riverpod                                                                               | One codebase iOS/Android/tablet, true offline, native camera/voice/GPS/biometrics |
| API layer        | API Gateway / BFF (Node) · REST + gRPC internal                                                                          | One secure entry, aggregates for mobile, rate limiting                            |
| Backend services | FastAPI (Python) for domain + AI · Node.js for realtime/WebSockets                                                       | Python for AI/ML fit; Node for sockets/push                                       |
| Async            | Redis Streams (MVP) → Kafka (scale) · Celery/BullMQ workers                                                              | Event-driven, background jobs                                                     |
| Database         | PostgreSQL (multi-tenant + RLS)                                                                                          | Relational integrity, JSONB flexibility, pgvector                                 |
| Cache/Queue      | Redis                                                                                                                    | Sessions, cache, rate limits, light queues                                        |
| Search           | OpenSearch/Elasticsearch                                                                                                 | Pricebook & customer search                                                       |
| Object storage   | S3-compatible (MinIO local)                                                                                              | Photos, PDFs, attachments                                                         |
| Vector           | pgvector (MVP) → Qdrant (scale)                                                                                          | AI memory / semantic pricebook                                                    |
| AI               | Anthropic Claude · OpenAI · Whisper/Google STT · Vision (Gemini)                                                         | Copilot, voice→quote, vision, OCR                                                 |
| Auth             | Clerk or Auth0 · OAuth · MFA · RBAC                                                                                      | Enterprise auth without building from scratch                                     |
| Payments         | Stripe · Square · ACH                                                                                                    | Deposits, installments, invoices                                                  |
| Infra            | Docker · K8s-ready · GitHub Actions · Cloudflare · Vercel (web) · Railway/Fly.io (MVP) → AWS/GCP (scale)                 | Cheap MVP, clean scale path                                                       |
| Observability    | OpenTelemetry · Prometheus · Grafana · Loki · Sentry                                                                     | Traces, metrics, logs, errors                                                     |

**Monorepo tooling (proposed, ADR-0001):** pnpm workspaces + Turborepo for JS/TS; `uv`/Poetry per Python service; Melos for Flutter packages.
