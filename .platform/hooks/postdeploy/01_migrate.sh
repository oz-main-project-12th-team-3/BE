#!/bin/bash
echo ">>> 01_migrate.sh is executing!"

echo ">>> Running database migrations..."
python manage.py migrate --noinput

echo ">>> Running collectstatic..."
python manage.py collectstatic --noinput