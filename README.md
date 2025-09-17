# 디지털 휴먼 AI 가상비서 서비스 구현

[🤩 우리 팀을 소개합니다](https://www.notion.so/268caf5650aa813fa60fe7775857251a?pvs=21)

[회의록 📅](https://www.notion.so/268caf5650aa817d9268e38a33445a41?pvs=21)

[팀 별 문서 공간 (4)](https://www.notion.so/268caf5650aa812d9d0ff38ca19dd1b5?pvs=21)

🚀 완전 자동화 GitHub 팀 프로젝트 설정
<br>
📋 구현 로드맵
<br>
🎯 1단계: 코드 품질 관리 시스템
<br>
🚀 2단계: 배포 자동화 파이프라인
<br>
👥 3단계: 팀 협업 자동화

## 🚀 개발 환경 설정 (Docker Compose)

이 프로젝트는 Docker Compose를 사용하여 일관된 개발 환경을 제공합니다.

### 📋 필수 조건

*   Docker Desktop (또는 Docker Engine 및 Docker Compose) 설치

### ⚙️ 시작하기

1.  **프로젝트 클론:**
    ```bash
    git clone [YOUR_REPOSITORY_URL]
    cd [YOUR_PROJECT_DIRECTORY]
    ```

2.  **.env 파일 설정:**
    `.env.example` 파일을 참조하여 프로젝트 루트에 `.env` 파일을 생성하고 필요한 환경 변수를 설정합니다.
    ```bash
    cp .env.example .env
    # 필요에 따라 .env 파일 내용 수정
    ```

3.  **Docker Compose로 서비스 시작:**
    모든 서비스를 빌드하고 시작합니다.
    ```bash
    docker-compose up --build
    ```
    (이후에는 `docker-compose up`만 사용해도 됩니다.)

4.  **데이터베이스 마이그레이션 적용:**
    컨테이너가 실행된 후, Django 마이그레이션을 적용하여 데이터베이스 스키마를 설정합니다.
    ```bash
    docker-compose exec web python manage.py migrate
    ```

5.  **슈퍼유저 생성 (선택 사항):**
    Django 관리자 페이지에 접근하기 위한 슈퍼유저를 생성합니다.
    ```bash
    docker-compose exec web python manage.py createsuperuser
    ```

6.  **애플리케이션 접근:**
    모든 서비스가 성공적으로 시작되면, 웹 애플리케이션은 `http://localhost:8000`에서 접근할 수 있습니다.

### 🛑 서비스 중지

모든 Docker 서비스를 중지하고 컨테이너를 제거합니다.
```bash
docker-compose down
```
데이터베이스 볼륨을 포함하여 모든 데이터를 완전히 제거하려면 다음 명령어를 사용합니다.
```bash
docker-compose down -v
```
