#!/bin/sh
set -euo pipefail

MODE="${APP_MODE:-api}"

# ---------- Функция ожидания Postgres ----------
wait_for_postgres() {
  log "Waiting for PostgreSQL..."

  for i in $(seq 1 30); do
    if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" >/dev/null 2>&1; then
      echo "PostgreSQL is ready"
      return 0
    fi

    log "PostgreSQL unavailable (attempt $i) - sleeping"
    sleep 2
  done

  log "PostgreSQL did not become ready in time"
  exit 1
}

# ---------- Функция ожидания Redis ----------
wait_for_redis() {
  log "Waiting for Redis..."

  for i in $(seq 1 30); do
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "Redis is ready"
      return 0
    fi

    log "Redis unavailable (attempt $i) - sleeping"
    sleep 2
  done

  log "Redis did not become ready in time"
  exit 1
}

# ---------- Функция миграций ----------
run_migrations() {
  log "Running migrations..."
  alembic upgrade head
}

# ---------- Запуск FastAPI ----------
start_api() {
  log "Starting FastAPI..."

  exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1
}

# ---------- Swarm secrets (если используются) ----------
if [ -n "${DB_AUTH_SERVICE_HOST_FILE:-}" ]; then
  DB_HOST=$(cat "$DB_AUTH_SERVICE_HOST_FILE")
fi

if [ -n "${DB_AUTH_SERVICE_PORT_FILE:-}" ]; then
  DB_PORT=$(cat "$DB_AUTH_SERVICE_PORT_FILE")
fi

if [ -n "${DB_AUTH_SERVICE_USER_FILE:-}" ]; then
  DB_USER=$(cat "$DB_AUTH_SERVICE_USER_FILE")
fi

if [ -n "${REDIS_HOST_FILE:-}" ]; then
  REDIS_HOST=$(cat "$REDIS_HOST_FILE")
fi

if [ -n "${REDIS_PORT_FILE:-}" ]; then
  REDIS_PORT=$(cat "$REDIS_PORT_FILE")
fi


# ---------- Ожидание сервисов ----------
wait_for_postgres

if [ "$MODE" = "migrate" ]; then
  run_migrations
  exit 0
fi

wait_for_redis

start_api