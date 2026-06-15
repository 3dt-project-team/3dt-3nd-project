import os
import shutil
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Azure Key Vault 부품
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

app = FastAPI(title="DataCops 품질 관제 플랫폼 API")

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔐 [개조] Azure Key Vault에서 DB와 Kafka 정보를 모두 가져와 시스템에 주입하는 함수
def initialize_platform_secrets():
    try:
        VAULT_URL = "https://kv-sense-team4.vault.azure.net/"
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=VAULT_URL, credential=credential)
        
        # 1. DB 정보 가져오기
        db_host = client.get_secret("db-host").value
        db_name = client.get_secret("db-name").value
        db_user = client.get_secret("db-user").value
        db_password = client.get_secret("db-password").value
        
        # 2. 🌟 [핵심] Kafka 정보도 금고에서 열기 (키볼트 내 실제 이름과 매칭하세요!)
        kafka_servers = client.get_secret("kafka-bootstrap-servers").value
        kafka_user = client.get_secret("kafka-username").value
        kafka_pass = client.get_secret("kafka-password").value
        
        # 3. 🔥 [치트키] 팀원의 코드가 읽을 수 있도록 시스템 환경변수에 실시간 주입!
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = kafka_servers
        os.environ["KAFKA_USERNAME"] = kafka_user
        os.environ["KAFKA_PASSWORD"] = kafka_pass
        
        print("✅ Key Vault에서 모든 DB 및 Kafka 접속 정보 주입 완료!")
        
        return {
            "host": db_host,
            "database": db_name,
            "user": db_user,
            "password": db_password,
            "port": 5432
        }
    except Exception as e:
        print(f"❌ Key Vault에서 설정을 로드하는데 실패했습니다: {e}")
        raise RuntimeError("치명적 보안 에러: Key Vault 설정을 읽을 수 없어 서버 가동을 전면 중단합니다.") from e

# 🚀 팀원 코드가 실행되기 전에 "먼저" 금고를 열고 환경변수를 채웁니다!
DB_CONFIG = initialize_platform_secrets()

# ── 🚨 환경변수가 주입된 후 안전하게 팀원 코드를 임포트 ──────────────────
from batch_producer import process_batch_file


# 📂 업로드 파일 임시 보관 폴더
UPLOAD_DIR = "/tmp" if os.name != "nt" else "./tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 📂 프론트엔드 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


# ── 📊 데이터 로직 API 영역 ──────────────────────────────────

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
        
        return {"status": "success", "count": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 연결 실패: {str(e)}")

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/login")
def login_user(login_info: LoginRequest):
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, email, password_hash, company_name, domain_name FROM web_users WHERE email = %s;", (login_info.email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user or login_info.password != "1234":
            raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
        
        return {
            "status": "success",
            "message": "로그인 성공",
            "user_info": {"company_name": user["company_name"], "domain_name": user["domain_name"]}
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


# ── 🚀 파일 업로드 및 카프카 적재 API 영역 ─────────────────────

@app.post("/api/upload")
async def upload_batch_file(
    company: str = Form(...),    
    domain: str = Form(...),     
    file: UploadFile = File(...) 
):
    filename = file.filename
    if not filename.lower().endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="CSV 또는 Excel 파일만 업로드 가능합니다.")

    temp_file_path = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임시 파일 저장 실패: {str(e)}")

    try:
        # 이 시점에는 시스템 환경변수에 카프카 정보가 박혀있으므로 완벽하게 동작합니다!
        result = process_batch_file(company=company, domain=domain, file_path=temp_file_path)
        
        if result.get("status") == "success":
            return {
                "status": "success",
                "message": f"성공적으로 {result['sent']:,}행이 카프카 토픽({result['topic']})으로 전송되었습니다.",
                "details": result
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("reason", "배치 적재 실패"))
            
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"배치 파이프라인 연동 중 예외 발생: {str(e)}")


# ── 🌐 프론트엔드 정적 페이지 서빙 영역 ────────────────────────

@app.get("/")
def read_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/login.html")
@app.get("/login")
def read_login():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

@app.get("/dashboard.html")
@app.get("/dashboard")
def read_dashboard():
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))

@app.get("/app.js")
def read_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))