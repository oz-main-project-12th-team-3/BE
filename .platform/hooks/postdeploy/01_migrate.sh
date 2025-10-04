#!/bin/bash
echo ">>> 01_migrate.sh is executing!"

echo ">>> Running database migrations..."
python3 manage.py migrate --noinput

echo ">>> Running collectstatic..."
python3 manage.py collectstatic --noinput