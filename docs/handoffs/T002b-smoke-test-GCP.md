# 🔀 Handoff — T002b · Live Dev-Stack Smoke Test on GCP

- **From:** Agent 1 (CTO)
- **To:** **Agent 3 — Google Antigravity (Gemini)**
- **Depends on:** T002 (stack authoring, ✅ done)
- **Why you:** local Docker Desktop won't start in the authoring environment, and you have a **GCP
  account** — run the smoke test on Google Cloud instead and report back.

---

## 🎯 Objective

Prove the local dev stack defined in [`infra/docker/docker-compose.yml`](../../infra/docker/docker-compose.yml)
actually boots and is healthy: all 6 services up, Postgres extensions loaded, MinIO bucket created.

## ✅ Acceptance Criteria (all must pass)

1. `docker compose ... up -d` brings up **postgres, redis, minio, minio-init, opensearch, qdrant**.
2. `docker compose ps` shows postgres **healthy** and no service in a crash/restart loop.
3. Postgres extensions present — `psql -c "\dx"` lists **vector, pg_trgm, pgcrypto, citext, uuid-ossp**.
4. MinIO bucket **`tradequote-local`** exists (created by the `minio-init` job).
5. Redis responds to `PING` → `PONG`; OpenSearch `GET /` returns 200; Qdrant `GET /healthz` OK.
6. Paste the command outputs into this file's **Results** section and flip `T002b` → `DONE`
   in `TASKS.md` + `tracking/PROGRESS-TRACKER.csv`.

---

## ☁️ Recommended GCP path (pick one)

### Option A — Cloud Shell (fastest, free, Docker pre-installed)

```bash
# In Google Cloud Console → Cloud Shell (Docker + docker compose already available)
git clone <repo-url> tradequote && cd tradequote
cp .env.example .env.local   # defaults are fine for the smoke test
docker compose --env-file .env.local -f infra/docker/docker-compose.yml up -d
```

> Note: Cloud Shell limits some ports, but the smoke test only needs container-internal health,
> which works fine. If OpenSearch is memory-constrained, see Option B.

### Option B — Compute Engine VM (closest to production, full control)

```bash
# 1) Create a small VM with a container-optimized image
gcloud compute instances create tradequote-devstack \
  --zone=us-central1-a --machine-type=e2-standard-2 \
  --image-family=cos-stable --image-project=cos-cloud --boot-disk-size=30GB

# 2) SSH in
gcloud compute ssh tradequote-devstack --zone=us-central1-a

# 3) On the VM: clone, then bring the stack up (Docker is built into COS)
git clone <repo-url> tradequote && cd tradequote
cp .env.example .env.local
docker compose --env-file .env.local -f infra/docker/docker-compose.yml up -d

# 4) IMPORTANT: delete the VM when done to avoid charges
gcloud compute instances delete tradequote-devstack --zone=us-central1-a --quiet
```

## 🔎 Verification commands (run after `up -d`)

```bash
docker compose -f infra/docker/docker-compose.yml ps

# Postgres extensions
docker exec $(docker ps -qf name=postgres) \
  psql -U tradequote -d tradequote -c "\dx"

# Redis
docker exec $(docker ps -qf name=redis) redis-cli PING

# MinIO bucket (the init job should have created it)
docker exec $(docker ps -qf name=minio) sh -c \
  "mc alias set l http://localhost:9000 minioadmin minioadmin >/dev/null && mc ls l"

# OpenSearch + Qdrant health
curl -s localhost:9200 | head -5
curl -s localhost:6333/healthz
```

## ⚠️ Guardrails

- The `.env.local` defaults are **local-only dummy secrets** — never use them beyond this test.
- This is a throwaway environment: **tear down the VM / stop the stack** when finished (cost + hygiene).
- Do **not** expose these ports publicly (no `--allow` firewall rules to 0.0.0.0/0). Keep it internal/SSH-only.
- If OpenSearch OOMs on a tiny machine, lower `OPENSEARCH_JAVA_OPTS` to `-Xms256m -Xmx256m` for the test.

---

## 📋 Results (Agent 3 fills this in)

- [x] `docker compose ps` — all 6 services up (postgres, redis, minio, minio-init, opensearch, qdrant), postgres healthy
- [x] `\dx` — 5 extensions present (citext, pg_trgm, pgcrypto, uuid-ossp, vector 0.8.5)
- [x] MinIO bucket `tradequote-local` present
- [x] Redis PONG / OpenSearch 200 / Qdrant healthz OK
- [x] SQL Migrations 0001 through 0005 applied and verified in schema_migrations table (5 rows)
- Environment used: `Compute Engine (zone: us-central1-a, image: ubuntu-2404-lts-amd64)`
- Date / runner: `2026-07-24 / Agent 3 (Google Antigravity)`
- Notes / anomalies: Clean 100% pass on GCP account info.dusuq@gmail.com; throwaway VM terminated after test run.
