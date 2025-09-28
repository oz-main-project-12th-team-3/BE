# 1단계: 빌드 스테이지
FROM python:3.10-slim AS builder

# 불필요한 pyc 파일 생성을 방지하고 로그를 표준 출력으로 전달
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 빌드에 필요한 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 명세 복사
COPY requirements.txt .

# 가상환경 생성
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# 휠 파일로 패키지 설치 캐시 생성(빨라지고 이미지 재사용 용이)
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt


# 2단계: 런타임 스테이지 - 실제 컨테이너 경량 실행환경
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 런타임에 필요한 최소 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

# 일반 사용자 생성 (루트 권한이 아닌 사용자로 앱 실행 권장)
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# 런타임 가상환경 생성
RUN python3 -m venv /home/appuser/.venv
ENV PATH="/home/appuser/.venv/bin:$PATH"

# 빌드 스테이지에서 생성된 휠 복사
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# 의존성 설치 (휠만 사용, 네트워크 비활성 상태에서도 설치 가능)
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt


## # two_factor 패키지 내부 URLs 문제 패치: two_factor/urls.py 패치 스크립트
#RUN python3 - <<EOF
#import re
#file_path = '/home/appuser/.venv/lib/python3.10/site-packages/two_factor/urls.py'
#with open(file_path, 'r') as f:
#    content = f.read()
#if 'app_name' not in content:
#    content = 'app_name = "two_factor"\\n' + content
#pattern = r"urlpatterns\\s*=\\s*\\((.+?),\\s*['\"]two_factor['\"]\\)"
#match = re.search(pattern, content, flags=re.DOTALL)
#if match:
#    urls_content = match.group(1).strip()
#    content = re.sub(pattern, f"urlpatterns = {urls_content}", content, flags=re.DOTALL)
#with open(file_path, 'w') as f:
#    f.write(content)
#EOF

# 어플리케이션 코드 복사
COPY . .

# 앱 경로권한 부여
RUN chown -R appuser:appuser /home/appuser/app

# 비루트 사용자로 실행 권한 변경
USER appuser

# 컨테이너 외부에 노출할 포트
EXPOSE 8000

# 애플리케이션 실행 명령 (ASGI 서버인 daphne 실행)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]