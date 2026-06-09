# web/backend/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

# 🌟 Azure Key Vault 연동을 위한 부품 추가!
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

app = FastAPI(title="DataOps 품질 관제 플랫폼 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔐 [보안 강화] Azure Key Vault에서 실시간으로 비밀번호를 꺼내오는 함수
def get_db_password_from_vault():
    try:
        # 우리 팀 Key Vault의 URL 주소
        VAULT_URL = "https://kv-sense-team4.vault.azure.net/"
        
        # DefaultAzureCredential은 현재 로그인된 자격을 자동으로 인식합니다.
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=VAULT_URL, credential=credential)
        
        # 아까 포털에 저장한 이름인 'db-password'로 비밀번호 추출
        secret = client.get_secret("db-password")
        return secret.value
    except Exception as e:
        print(f"❌ Key Vault에서 비밀번호를 가져오는데 실패했습니다: {e}")
        # 로컬 테스트 시 권한 에러가 나면 하드코딩으로 임시 우회할 수 있도록 에러 처리를 해둡니다.
        return "여기에_임시_비밀번호" 

# 금고에서 꺼내온 비밀번호를 변수에 안전하게 담습니다.
REAL_DB_PASSWORD = get_db_password_from_vault()

# 🔐 데이터베이스 접속 정보 (이제 비밀번호가 유출되지 않습니다!)
DB_CONFIG = {
    "host": "datacops-web-db.postgres.database.azure.com",
    "database": "postgres",
    "user": "azureadmin",
    "password": REAL_DB_PASSWORD,  # ★ 금고에서 가져온 비밀번호 주입
    "port": 5432
}


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