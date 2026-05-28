#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
COMPOSE_CMD=("$CONTAINER_RUNTIME" compose)

if ! command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1; then
  echo "$CONTAINER_RUNTIME is required to bootstrap local infrastructure." >&2
  exit 1
fi

PROFILE="${1:-local}"
case "$PROFILE" in
  local)
    APP_ENV_VALUE="development"
    DB_NAME="template_local"
    ;;
  staging)
    APP_ENV_VALUE="staging"
    DB_NAME="template_staging"
    ;;
  *)
    echo "Unsupported bootstrap profile: $PROFILE (expected: local|staging)" >&2
    exit 1
    ;;
esac

./scripts/copy_env_templates.sh "$PROFILE"

echo "Installing backend dependencies..."
(cd backend && uv sync --all-groups)

echo "Installing frontend dependencies..."
(cd frontend && npm ci)

if command -v flutter >/dev/null 2>&1; then
  echo "Installing mobile dependencies..."
  (cd mobile && flutter pub get)
else
  echo "Flutter is not installed; skipping mobile dependency setup."
fi

echo "Starting required infrastructure services (postgres, redis)..."
  "${COMPOSE_CMD[@]}" down --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE_CMD[@]}" up -d db redis

echo "Waiting for postgres to accept connections..."
until "${COMPOSE_CMD[@]}" exec -T db pg_isready -U postgres >/dev/null 2>&1; do
  sleep 1
  printf '.'
done
printf '\n'

echo "Ensuring bootstrap database '$DB_NAME' exists..."
"${COMPOSE_CMD[@]}" exec -T db psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || "${COMPOSE_CMD[@]}" exec -T db psql -U postgres -c "CREATE DATABASE ${DB_NAME};"

echo "Applying backend migrations to ${DB_NAME}..."
(
  cd backend
  APP_ENV="$APP_ENV_VALUE" \
  POSTGRES_SERVER=localhost \
  POSTGRES_USER=postgres \
  POSTGRES_PASSWORD=postgres \
  POSTGRES_DB="$DB_NAME" \
  DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:15432/${DB_NAME}" \
  SYNC_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:15432/${DB_NAME}" \
  REDIS_URL="redis://localhost:16379/0" \
  CELERY_BROKER_URL="redis://localhost:16379/0" \
  CELERY_RESULT_BACKEND="redis://localhost:16379/0" \
  uv run task migrate
)

echo "Bootstrap complete for profile '$PROFILE'."
echo "Run services with: make backend-dev, make frontend-dev, make mobile-dev"
