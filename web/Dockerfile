FROM python:3.11-slim

WORKDIR /app

# 1. 웹 서비스 구동에 필요한 핵심 패키지 사전 설치
RUN pip install --no-cache-dir fastapi uvicorn azure-identity azure-keyvault-secrets psycopg2-binary requests

# 2. 백엔드와 프론트엔드 폴더를 통째로 상자 안으로 복사
COPY frontend/ ./frontend/
COPY backend/ ./backend/

# 3. 명령어를 실행할 기본 작업 디렉터리를 백엔드로 이동
WORKDIR /app/backend

# 4. 컨테이너가 사용할 포트 개방
EXPOSE 8000

# 5. 컨테이너가 켜질 때 서버를 실행하는 명령어
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]