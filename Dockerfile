# Python 3.10 버전을 기반으로 이미지를 생성합니다.
FROM python:3.10

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 작업 디렉토리를 /app으로 설정합니다.
WORKDIR /app

# requirements.txt 파일을 복사하고 패키지를 설치합니다.
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# 현재 디렉토리의 모든 파일을 /app에 복사합니다.
COPY . /app/
