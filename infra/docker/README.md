# Local Development Stack (T002)

Backing services for local development. Requires **Docker Desktop running**.

## Start / stop

```bash
pnpm dev:up      # start all services (detached)
pnpm dev:logs    # tail logs
pnpm dev:down    # stop
pnpm dev:reset   # stop + wipe volumes (fresh DB)
```

Or directly: `docker compose --env-file .env.local -f infra/docker/docker-compose.yml up -d`

## Services & ports

| Service    | Image                            | Port(s)                    | Purpose                                                               |
| ---------- | -------------------------------- | -------------------------- | --------------------------------------------------------------------- |
| postgres   | `pgvector/pgvector:pg16`         | 5432                       | Primary DB (+ `vector`, `pg_trgm`, `pgcrypto`, `citext`, `uuid-ossp`) |
| redis      | `redis:7-alpine`                 | 6379                       | Cache, queues, rate limits                                            |
| minio      | `minio/minio`                    | 9000 (API), 9001 (console) | S3-compatible object storage                                          |
| minio-init | `minio/mc`                       | —                          | One-shot: auto-creates the dev bucket                                 |
| opensearch | `opensearchproject/opensearch:2` | 9200                       | Search (pricebook/customers)                                          |
| qdrant     | `qdrant/qdrant`                  | 6333                       | Vector DB (alt to pgvector)                                           |

## First-run init

- `init/postgres/01-extensions.sql` runs automatically on first DB creation and enables all required extensions.
- `minio-init` waits for MinIO then creates the bucket from `S3_BUCKET` (default `tradequote-local`).

## Verify it's up

```bash
docker compose -f infra/docker/docker-compose.yml ps
docker exec -it docker-postgres-1 psql -U tradequote -d tradequote -c "\dx"   # list extensions
# MinIO console: http://localhost:9001  (minioadmin / minioadmin)
# OpenSearch:    http://localhost:9200
```

## Notes

- All defaults come from `.env.local`; never commit real secrets.
- On Windows, ensure Docker Desktop has finished starting (whale icon steady) before `pnpm dev:up`.
