# 1단계: 빌드 스테이지
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 빌드에 필요한 시스템 의존성 설치
# libpq-dev, gcc (패키지 빌드용), postgresql-client (pg_isready 명령 사용용)
# wget은 런타임에 필요하므로 런타임 스테이지에서 설치
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 명세 복사
COPY requirements.txt .

# 가상환경 생성 및 경로 설정
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# 휠 파일로 패키지 설치 캐시 생성
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# 최적화: 빌드에만 사용된 gcc 및 개발 도구 정리
RUN apt-get purge -y --auto-remove gcc && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------------------
# 2단계: 런타임 스테이지 - 실제 컨테이너 경량 실행환경
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 런타임에 필요한 최소 의존성 설치 (DB 대기 및 healthcheck를 위해 필수)
# libpq-dev: DB 연결 라이브러리 (psycopg2 사용)
# postgresql-client: pg_isready 명령어 사용 가능하도록
# wget: web 서비스 healthcheck (docker-compose.yml에서 사용)
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev postgresql-client wget && rm -rf /var/lib/apt/lists/*

# 일반 사용자 생성
RUN useradd --no-create-home appuser

WORKDIR /app

# 빌드 스테이지에서 생성된 휠 복사
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# 시스템 Python 환경에 직접 의존성 설치
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# 💡 start.sh 스크립트 복사 및 실행 권한 부여 (DB 대기 및 마이그레이션 자동화)
COPY start.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/start.sh

# 어플리케이션 코드 복사 (보안 강화를 위해 명시적으로 지정)
COPY --chown=appuser:appuser ./ai /app/ai/
COPY --chown=appuser:appuser ./chat /app/chat/
COPY --chown=appuser:appuser ./config /app/config/
COPY --chown=appuser:appuser ./frontend /app/frontend/
COPY --chown=appuser:appuser ./notifications /app/notifications/
COPY --chown=appuser:appuser ./payments /app/payments/
COPY --chown=appuser:appuser ./schedule /app/schedule/
COPY --chown=appuser:appuser ./search /app/search/
COPY --chown=appuser:appuser ./two_factor_wrapper /app/two_factor_wrapper/
COPY --chown=appuser:appuser ./users /app/users/
COPY --chown=appuser:appuser ./manage.py /app/manage.py
COPY --chown=appuser:appuser ./pyproject.toml /app/pyproject.toml

# 정적 파일 수집
RUN python3 manage.py collectstatic --noinput

# 미디어 디렉토리 생성
RUN mkdir -p /app/media

# 앱 경로 권한 부여
RUN chown -R appuser:appuser /app

# 보안 강화: 애플리케이션 파일 및 디렉토리에서 쓰기 권한 제거
RUN chmod -R a-w /app

# collectstatic을 위해 staticfiles 디렉토리와 media 디렉토리에 쓰기 권한 부여
RUN chmod -R u+w /app/staticfiles /app/media

# 비루트 사용자로 실행 권한 변경
USER appuser

# 컨테이너 외부에 노출할 포트
EXPOSE 8000

# ✅ CMD 추가 (start.sh가 있다면 이것을 실행)
CMD ["/usr/local/bin/start.sh"]