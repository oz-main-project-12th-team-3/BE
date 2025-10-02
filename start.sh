#!/bin/bash
# start.sh
set -e

# 환경변수로 DB 체크 제어 (Elastic Beanstalk에서는 SKIP_DB_CHECK=true 설정)
SKIP_DB_CHECK=${SKIP_DB_CHECK:-false}

if [ "$SKIP_DB_CHECK" = "false" ]; then
  echo "Waiting for PostgreSQL to be ready..."
  
  DB_HOST=${DB_HOST:-db}
  DB_PORT=${DB_PORT:-5432}
  DB_USER=${POSTGRES_USER:-myuser}
  
  MAX_TRIES=30
  TRIES=0
  
  while ! pg_isready -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER}; do
    TRIES=$((TRIES+1))
    if [ $TRIES -ge $MAX_TRIES ]; then
      echo "ERROR: Database not ready after ${MAX_TRIES} seconds"
      exit 1
    fi
    echo "Waiting for database... (${TRIES}/${MAX_TRIES})"
    sleep 1
  done
  
  echo "PostgreSQL is ready and accessible."
else
  echo "Skipping database readiness check (SKIP_DB_CHECK=true)"
fi

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
