# 1단계 빌드 스테이지
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt


# 2단계 런타임 스테이지
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
WORKDIR /home/appuser/app

RUN python3 -m venv /home/appuser/.venv
ENV PATH="/home/appuser/.venv/bin:$PATH"

COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY . .

# two_factor 패키지 내부 URLs 문제 패치: two_factor/urls.py 패치 스크립트
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

RUN chown -R appuser:appuser /home/appuser/app

USER appuser

EXPOSE 8000 8001

# CMD는 docker-compose.yml에서 각각 명령어로 지정
