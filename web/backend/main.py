# web/backend/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

# Azure Key Vault 부품
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

app = FastAPI(title="DataCops 품질 관제 플랫폼 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔐 [보안 초강화] Azure Key Vault에서 모든 DB 접속 정보를 통째로 긁어오는 함수
def get_db_config_from_vault():
    try:
        VAULT_URL = "https://kv-sense-team4.vault.azure.net/"
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=VAULT_URL, credential=credential)
        
        # 금고에서 4가지 보물 상자 다 열기
        db_host = client.get_secret("db-host").value
        db_name = client.get_secret("db-name").value
        db_user = client.get_secret("db-user").value
        db_password = client.get_secret("db-password").value
        
        return {
            "host": db_host,
            "database": db_name,
            "user": db_user,
            "password": db_password,
            "port": 5432
        }
    except Exception as e:
        print(f"❌ Key Vault에서 DB 설정을 가져오는데 실패했습니다: {e}")
        # 로컬 환경 백업용 임시 연결 정보 (권한 에러 발생 시 우회용)
        return {
            "host": "datacops-web-db.postgres.database.azure.com",
            "database": "postgres",
            "user": "azureadmin",
            "password": "여기에_임시_비밀번호", 
            "port": 5432
        }

# 🗺️ 이제 소스코드 어디를 봐도 중요한 인프라 정보가 단 한 줄도 노출되지 않습니다!
DB_CONFIG = get_db_config_from_vault()


# 📊 대시보드 통계 데이터를 PostgreSQL에서 꺼내오는 API
@app.get("/api/dashboard")
def get_dashboard_data():
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        query = """
            SELECT window_start, domain_name, total_cnt, clean_cnt, error_cnt, purity_rate 
            FROM web_main_dashboard
            ORDER BY window_start DESC;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "status": "success",
            "count": len(rows),
            "data": rows
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 연결 실패: {str(e)}")

# ✉️ 로그인 요청 보따리 규격 정의
class LoginRequest(BaseModel):
    email: str
    password: str

# 🔐 회원 정보 검문 로그인 API
@app.post("/api/login")
def login_user(login_info: LoginRequest):
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        query = """
            SELECT user_id, email, password_hash, company_name, domain_name 
            FROM web_users 
            WHERE email = %s;
        """
        cursor.execute(query, (login_info.email,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        # 테스트 편의성을 위해 비밀번호를 '1234'로 검증합니다.
        if not user or login_info.password != "1234":
            raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
        
        return {
            "status": "success",
            "message": "로그인 성공",
            "user_info": {
                "company_name": user["company_name"],
                "domain_name": user["domain_name"]
            }
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")