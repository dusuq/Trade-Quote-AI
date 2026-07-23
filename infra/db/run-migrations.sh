#!/usr/bin/env bash
# Apply ordered SQL migrations to the target database.
# Usage: DATABASE_URL=postgresql://tradequote:tradequote@localhost:5432/tradequote ./run-migrations.sh
# Requires: psql on PATH and a running Postgres (see infra/docker). Idempotent.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)/migrations"
: "${DATABASE_URL:?Set DATABASE_URL (e.g. from .env.local)}"

echo "Applying migrations from $DIR"
for f in "$DIR"/[0-9]*.sql; do
  echo "  → $(basename "$f")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$f"
done

echo "Applied versions:"
psql "$DATABASE_URL" -Atc "SELECT version FROM schema_migrations ORDER BY version;"
echo "Done."
