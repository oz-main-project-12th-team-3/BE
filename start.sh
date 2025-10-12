#!/bin/bash
set -e

# 환경 변수 설정
export PYTHONPATH=/app:$PYTHONPATH
export DJANGO_SETTINGS_MODULE=config.settings

# 작업 디렉토리 확인
cd /app

echo "Current directory: $(pwd)"
echo "PYTHONPATH: $PYTHONPATH"

if [ -n "$RDS_HOSTNAME" ]; then
    echo "✅ Production environment detected (RDS_HOSTNAME is set)."
    
    # RDS 연결 대기 (프로덕션에서만)
    echo "Waiting for database to be ready..."
    MAX_RETRIES=30
    RETRY_COUNT=0
    
    until pg_isready -h "$RDS_HOSTNAME" -p "$RDS_PORT" -U "$RDS_USERNAME" > /dev/null 2>&1 || [ $RETRY_COUNT -eq $MAX_RETRIES ]; do
        echo "Database is unavailable - sleeping (attempt $((RETRY_COUNT+1))/$MAX_RETRIES)"
        RETRY_COUNT=$((RETRY_COUNT+1))
        sleep 2
    done
    
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo "❌ Database connection timeout!"
        echo "RDS_HOSTNAME: $RDS_HOSTNAME"
        echo "RDS_PORT: $RDS_PORT"
        echo "RDS_USERNAME: $RDS_USERNAME"
        exit 1
    fi
    
    echo "✅ Database is ready!"
    echo "Running database migrations..."
    python3 manage.py migrate --noinput
else
    echo "ℹ️ Local environment detected. Skipping migrations."
    # 로컬에서는 pg_isready 체크를 건너뛰고 바로 마이그레이션 실행
    echo "Running database migrations for local environment..."
    python3 manage.py migrate --noinput
fi

echo "Collecting static files..."
python3 manage.py collectstatic --noinput

echo "Starting Daphne ASGI server..."
exec python3 -m daphne -b 0.0.0.0 -p 8000 config.asgi:application
