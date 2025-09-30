# 1단계: 빌드 스테이지
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 빌드에 필요한 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 명세 복사
COPY requirements.txt .

# 가상환경 생성 및 경로 설정 (선택적이지만, pip wheel을 실행하는 환경)
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# 휠 파일로 패키지 설치 캐시 생성
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# 💡 최적화: 빌드에만 사용된 gcc 및 개발 도구 정리
RUN apt-get purge -y --auto-remove gcc && rm -rf /var/lib/apt/lists/*


# ----------------------------------------------------------------------------------
# 2단계: 런타임 스테이지 - 실제 컨테이너 경량 실행환경
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 런타임에 필요한 최소 의존성 설치 (libpq-dev는 필요함)
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

# 일반 사용자 생성 (홈 디렉토리는 기본 WORKDIR로 대체)
RUN useradd --no-create-home appuser

# 💡 WORKDIR 단순화
WORKDIR /app

# 빌드 스테이지에서 생성된 휠 복사
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# 💡 venv 없이 시스템 Python 환경에 직접 의존성 설치
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# 💡 two_factor 패키지 내부 URLs 문제 패치: two_factor/urls.py 수정
#    목표: urlpatterns = (path(...), 'two_factor') 형태를
#    urlpatterns = (path(...),) 형태로 변환하여 urls.E004 오류를 해결
RUN python3 - <<EOF
import re
import sys
from pathlib import Path

# /usr/local/lib/python3.10/site-packages 경로 설정 (시스템 환경에 설치)
# 주의: 이 경로는 python:3.10-slim 이미지의 표준 site-packages 경로입니다.
file_path = Path('/usr/local/lib') / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages' / 'two_factor' / 'urls.py'

if not file_path.exists():
    print(f"Error: two_factor/urls.py not found at {file_path}", file=sys.stderr)
    sys.exit(1)

with open(file_path, 'r') as f:
    content = f.read()

# 1. 'app_name'이 없는 경우 추가 (앱 이름 설정 보장)
if 'app_name' not in content:
    content = 'app_name = "two_factor"\\n' + content

# 2. 'urlpatterns = ( ... , "two_factor")' 튜플 형태를 찾아 마지막 요소를 제거합니다.
#    패턴: urlpatterns = ( ... , ['"]two_factor['"])
#    (.+?)는 URL 패턴들을 비탐욕적으로 캡쳐합니다.
pattern = r"urlpatterns\s*=\s*\((.+?),(\s*['\"]two_factor['\"]\s*)\)"

def replace_tuple(match):
    # match.group(1)은 튜플의 내부 URL 패턴들입니다.
    # match.group(2)는 오류를 유발하는, two_factor 문자열입니다.
    urls_content = match.group(1).strip()

    # 튜플을 (요소1, 요소2, ...) 형태로 변환하여 오류를 유발하는 요소를 제거
    return f"urlpatterns = ({urls_content})"

content = re.sub(pattern, replace_tuple, content, flags=re.DOTALL)

with open(file_path, 'w') as f:
    f.write(content)

print(f"Successfully patched {file_path}")
EOF

# 어플리케이션 코드 복사
COPY --chown=appuser:appuser . .

# 정적 파일 수집 (시스템 PATH 사용)
RUN python3 manage.py collectstatic --noinput

# 앱 경로 권한 부여
RUN chown -R appuser:appuser /app

# 비루트 사용자로 실행 권한 변경
USER appuser

# 컨테이너 외부에 노출할 포트
EXPOSE 8000

# 애플리케이션 실행 명령 (ASGI 서버인 daphne 실행)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]