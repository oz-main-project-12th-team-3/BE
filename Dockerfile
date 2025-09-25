# 1단계: 빌드 스테이지
FROM python:3.10-slim AS builder

# Python 출력 설정: pyc 파일 생성 방지 및 버퍼링 비활성화
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Astral uv 공식 이미지에서 uv 바이너리 복사
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 빌드에 필요한 운영체제 라이브러리 설치
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) 의존성 정의 파일만 먼저 복사 (빌드 캐시 최적화 목적)
COPY requirements.in .

# 2) uv 명령어로 requirements.in을 requirements.txt로 컴파일 (pip-tools 의존성 컴파일 대체)
RUN uv pip compile requirements.in -o requirements.txt

# 3) uv로 가상환경 생성
RUN uv venv /venv

# 4) 가상환경 경로를 PATH에 추가
ENV PATH="/venv/bin:$PATH"

# 5) uv pip wheel 명령어로 휠 캐시 생성 (휠을 /wheels 에 저장하여 재사용 효율화)
# 휠 캐시 대신 직접 가상환경에 설치
RUN uv pip install --no-cache-dir -r requirements.txt


# 6) 애플리케이션 소스 복사 (의존성 설치 이후 복사하여 소스 코드 변경 시 의존성 레이어가 캐시됨을 방지)
COPY . .


# 2단계: 런타임 스테이지
FROM python:3.10-slim

# Python 출력 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 런타임에 필요한 라이브러리 설치
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

# uv 바이너리 복사
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 비루트 사용자 생성 및 작업 디렉터리 설정
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# uv로 런타임 가상환경 생성
RUN uv venv /home/appuser/.venv

# 가상환경 경로 PATH에 추가
ENV PATH="/home/appuser/.venv/bin:$PATH"

# 빌드 스테이지에서 생성한 휠 복사
COPY --from=builder /wheels /wheels

# 컴파일된 requirements.txt 복사
COPY --from=builder /app/requirements.txt .

# uv를 이용해 휠 기반 의존성 설치 (네트워크 없이 설치 가능)
RUN uv pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt


# two_factor 패키지 내 urls.py 파일 문제 패치 스크립트 실행
RUN python3 - <<EOF
import re
file_path = '/home/appuser/.venv/lib/python3.10/site-packages/two_factor/urls.py'
with open(file_path, 'r') as f:
    content = f.read()
if 'app_name' not in content:
    content = 'app_name = "two_factor"\\n' + content
pattern = r"urlpatterns\\s*=\\s*\\((.+?),\\s*['\"]two_factor['\"]\\)"
match = re.search(pattern, content, flags=re.DOTALL)
if match:
    urls_content = match.group(1).strip()
    content = re.sub(pattern, f"urlpatterns = {urls_content}", content, flags=re.DOTALL)
with open(file_path, 'w') as f:
    f.write(content)
EOF

# 앱 소스 권한 변경 (비루트 사용자 실행을 위해)
RUN chown -R appuser:appuser /home/appuser/app

# 비루트 사용자로 컨테이너 실행 전환
USER appuser

# 컨테이너 외부에 노출할 포트
EXPOSE 8000

# ASGI 서버 실행 (daphne)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
