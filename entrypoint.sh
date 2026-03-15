#!/bin/sh
set -e

# --- Ждём Postgres ---
echo "Waiting for Postgres at $DB_HOST:$DB_PORT..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER"; do
  echo "Postgres is unavailable - sleeping"
  sleep 2
done

# --- Ждём Redis ---
echo "Waiting for Redis at $REDIS_HOST:$REDIS_PORT..."
while ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; do
  echo "Redis is unavailable - sleeping"
  sleep 2
done

# --- Выполняем миграции ---
echo "Running migrations..."
alembic upgrade head

# --- Запуск FastAPI ---
echo "Starting FastAPI..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
