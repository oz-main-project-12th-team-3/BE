#!/bin/bash
# start.sh

exec > /var/log/my_app_startup.log 2>&1

set -e

# Elastic Beanstalk 환경에서는 RDS_HOSTNAME 변수가 존재합니다.
# 이 변수의 존재 여부로 실제 배포 환경인지 로컬 환경인지 구분합니다.
if [ -n "$RDS_HOSTNAME" ]; then
    echo "✅ Production environment detected (RDS_HOSTNAME is set)."
    echo "Running database migrations..."
    python3 manage.py migrate --noinput || { echo "MIGRATE FAILED"; exit 1; }
    echo "Migrations completed."
else
    echo "ℹ️ Local environment detected (RDS_HOSTNAME is not set). Skipping migrations."
fi

echo "Collecting static files..."
python3 manage.py collectstatic --noinput || { echo "COLLECTSTATIC FAILED"; exit 1; }
echo "Collectstatic completed."

echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
