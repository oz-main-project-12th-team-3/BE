# 1단계: 빌드 스테이지
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 빌드에 필요한 시스템 의존성 설치
# libpq-dev: PostgreSQL 클라이언트 라이브러리 (psycopg2 빌드용)
# gcc: C 컴파일러 (Python 패키지 빌드용)
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

# 런타임에 필요한 최소 의존성 설치 (PostgreSQL 연결을 위해 libpq-dev 필요)
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

# 일반 사용자 생성
RUN useradd --no-create-home appuser

WORKDIR /app

# 빌드 스테이지에서 생성된 휠 복사
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# 시스템 Python 환경에 직접 의존성 설치
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# 💡 two_factor 패키지 내부 URLs 문제 패치
#    목표: `urlpatterns = (path(...), 'two_factor')` 형태를
#    `urlpatterns = (path(...),)` 형태로 변환하고 `app_name`을 별도로 정의하여 `urls.E004` 오류 해결
RUN python3 - <<EOF
import re
import sys
from pathlib import Path

# 파이썬 버전 기반으로 site-packages 경로를 찾음
# /usr/local/lib/python3.10/site-packages
site_packages_dir = Path('/usr/local/lib') / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
file_path = site_packages_dir / 'two_factor' / 'urls.py'

if not file_path.exists():
    print(f"Error: two_factor/urls.py not found at {file_path}", file=sys.stderr)
    # 설치 경로는 Dockerfile에 하드코딩되어 있으므로, 문제가 있으면 실패해야 함
    # sys.exit(1) # 실제 운영 환경에서는 안전을 위해 오류 시 빌드 실패가 좋음

with open(file_path, 'r') as f:
    content = f.read()

# 1. 'urlpatterns = (... , 'two_factor')' 패턴을 찾습니다.
pattern = r"(urlpatterns\s*=\s*\((.+?)),\s*['\"]two_factor['\"]\s*\)"

def replace_tuple(match):
    # 'two_factor' 문자열만 제거하고 튜플을 닫습니다.
    return match.group(1) + ')'

content = re.sub(pattern, replace_tuple, content, flags=re.DOTALL)

# 2. app_name 정의 추가 (이전에는 튜플의 마지막 요소로 사용됨)
# 주의: 이미 app_name이 정의되어 있을 가능성이 낮으므로, 단순 추가로 처리
if 'app_name = "two_factor"' not in content:
    content = 'app_name = "two_factor"\\n' + content

with open(file_path, 'w') as f:
    f.write(content)

print(f"Successfully patched {file_path}")
EOF

# 어플리케이션 코드 복사
COPY --chown=appuser:appuser . .

# 정적 파일 수집
RUN python3 manage.py collectstatic --noinput

# 앱 경로 권한 부여
RUN chown -R appuser:appuser /app

# 비루트 사용자로 실행 권한 변경
USER appuser

# 컨테이너 외부에 노출할 포트
EXPOSE 8000

# 애플리케이션 실행 명령
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]