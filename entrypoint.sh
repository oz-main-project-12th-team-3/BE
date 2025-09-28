#!/bin/sh

# 정적 파일 권한 변경
chown -R appuser:appuser /home/appuser/app/static

# 전달받은 명령어 실행
exec "$@"

# docker compose run -u root --rm gunicorn python manage.py collectstatic --noinput
# 위의 명령어 실행 후 권한 문제 발생 시
# sudo chown -R 1000:1000 ./static ./media