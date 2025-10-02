#!/bin/bash
# start.sh
set -e # 오류 발생 시 즉시 종료

# -----------------------------------------------------
# 1. DB 연결 준비될 때까지 대기
# -----------------------------------------------------
echo "Waiting for PostgreSQL to be ready..."

# pg_isready를 사용하여 DB에 연결 가능한지 확인
while ! pg_isready -h db -U ${POSTGRES_USER:-myuser}; do
  sleep 1
done
echo "PostgreSQL is ready and accessible."

# -----------------------------------------------------
# 2. 마이그레이션 실행 (ProgrammingError 해결)
# -----------------------------------------------------
echo "Running database migrations..."
python manage.py migrate --noinput

# -----------------------------------------------------
# 3. 애플리케이션 서버 실행
# -----------------------------------------------------
echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application