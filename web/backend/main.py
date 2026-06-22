import io
import json
import os
import shutil
from datetime import datetime
from typing import List, Optional

import pandas as pd
import psycopg2

# Azure Key Vault 부품
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

app = FastAPI(title="DataCops 품질 관제 플랫폼 API")

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 🔐 Azure Key Vault에서 DB, Kafka, Storage 정보를 모두 가져와 시스템에 주입하는 함수
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

        # 2. Kafka 정보도 금고에서 열기
        kafka_servers = client.get_secret("kafka-bootstrap-servers").value
        kafka_user = client.get_secret("kafka-username").value
        kafka_pass = client.get_secret("kafka-password").value

        # 3. 애저 스토리지 연결 문자열도 금고에서 안전하게 확보
        storage_conn = client.get_secret("storage-connection-string").value

        # 시스템 환경변수에 실시간 주입
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = kafka_servers
        os.environ["KAFKA_USERNAME"] = kafka_user
        os.environ["KAFKA_PASSWORD"] = kafka_pass
        os.environ["AZURE_STORAGE_CONNECTION_STRING"] = storage_conn

        print("✅ Key Vault에서 모든 DB, Kafka, Storage 접속 정보 주입 완료!")

        return {
            "host": db_host,
            "database": db_name,
            "user": db_user,
            "password": db_password,
            "port": 5432,
        }
    except Exception as e:
        print(f"❌ Key Vault에서 설정을 로드하는데 실패했습니다: {e}")
        raise RuntimeError(
            "치명적 보안 에러: Key Vault 설정을 읽을 수 없어 서버 가동을 전면 중단합니다."
        ) from e


# 서버 기동 전 안전하게 비밀 키 정보 로드 및 도커 환경 설정 정합성 부여
DB_CONFIG = initialize_platform_secrets()

# 글로벌 블롭 스토리지 클라이언트 초기화
blob_service_client = BlobServiceClient.from_connection_string(
    os.environ["AZURE_STORAGE_CONNECTION_STRING"]
)


def ensure_rule_versions_table():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rule_versions (
            id SERIAL PRIMARY KEY,
            domain VARCHAR(255) NOT NULL,
            version_num INT NOT NULL,
            rules_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            created_by VARCHAR(255),
            note VARCHAR(500),
            is_active BOOLEAN DEFAULT FALSE,
            UNIQUE(domain, version_num)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


ensure_rule_versions_table()


def get_redis_client():
    from redis.cluster import ClusterNode, RedisCluster

    credential = DefaultAzureCredential()
    from azure.keyvault.secrets import SecretClient

    kv = SecretClient(vault_url="https://kv-sense-team4.vault.azure.net/", credential=credential)
    host = kv.get_secret("redis-host").value
    port = int(kv.get_secret("redis-port").value)
    password = kv.get_secret("redis-password").value
    return RedisCluster(
        startup_nodes=[ClusterNode(host, port)],
        password=password,
        ssl=True,
        ssl_check_hostname=False,
        decode_responses=True,
        skip_full_coverage_check=True,
        socket_connect_timeout=10,
        socket_timeout=10,
    )


def verify_domain_ownership(email: str, domain: str):
    """유저가 해당 도메인을 소유하는지 검증. 없으면 403."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM data_sources ds
        JOIN web_users wu ON ds.user_id = wu.user_id
        WHERE wu.email = %s AND ds.bronze_folder = %s
    """,
        (email, domain),
    )
    ok = cur.fetchone()
    cur.close()
    conn.close()
    if not ok:
        raise HTTPException(status_code=403, detail="해당 도메인에 대한 접근 권한이 없습니다.")


def get_next_version(domain: str, conn) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(MAX(version_num), 0) + 1 FROM rule_versions WHERE domain = %s", (domain,)
    )
    v = cur.fetchone()[0]
    cur.close()
    return v


def save_new_version(domain: str, rules: dict, created_by: str, note: str, activate: bool = True):
    """rule_versions에 새 버전 저장하고 Redis 업데이트."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    version_num = get_next_version(domain, conn)
    if activate:
        cur.execute("UPDATE rule_versions SET is_active = FALSE WHERE domain = %s", (domain,))
    cur.execute(
        """
        INSERT INTO rule_versions (domain, version_num, rules_json, created_by, note, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
    """,
        (domain, version_num, json.dumps(rules, ensure_ascii=False), created_by, note, activate),
    )
    conn.commit()
    cur.close()
    conn.close()

    if activate:
        r = get_redis_client()
        rules["_version"] = version_num
        r.set(f"gx_rules:{domain.lower()}", json.dumps(rules, ensure_ascii=False))

    return version_num


def get_user_domain(email: str) -> str:
    """이메일로 DB에서 domain_name 조회. 없으면 404."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT domain_name FROM web_users WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")
    return row["domain_name"]


# ── 🚨 환경변수가 주입된 후 안전하게 팀원 코드를 임포트 ──────────────────
from batch_producer import process_batch_file  # noqa: E402

# 📂 업로드 파일 임시 보관 폴더
UPLOAD_DIR = "/tmp" if os.name != "nt" else "./tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 📂 프론트엔드 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


# ── 🛠️ 격리 및 마스터 데이터 관리를 위한 추가 Pydantic 모델 & 헬퍼 함수 ──


class QuarantineActionRequest(BaseModel):
    row_ids: Optional[List[str]] = None
    reason: Optional[str] = "사유 기입 누락"


def _log_quarantine_action(domain: str, row_ids: list, action: str, reason: str):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO quarantine_actions (domain, row_ids, action, reason, reviewed_at)
            VALUES (%s, %s, %s, %s, now())
        """,
            (domain, json.dumps(row_ids) if row_ids else None, action, reason),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[WARN] 데이터 관제 액션 이력 PostgreSQL 적재 실패: {e}")


def _get_blob_df(container: str, prefix: str) -> pd.DataFrame:
    container_client = blob_service_client.get_container_client(container)
    blob_list = container_client.list_blobs(name_starts_with=prefix)

    dfs = []
    for blob in blob_list:
        if blob.name.endswith(".parquet"):
            blob_client = container_client.get_blob_client(blob.name)
            data = blob_client.download_blob().readall()
            dfs.append(pd.read_parquet(io.BytesIO(data)))

    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _write_blob_df(container: str, blob_path: str, df: pd.DataFrame):
    out_buffer = io.BytesIO()
    df.to_parquet(out_buffer, index=False, engine="pyarrow")
    out_buffer.seek(0)

    blob_client = blob_service_client.get_blob_client(container=container, blob=blob_path)
    blob_client.upload_blob(out_buffer.read(), overwrite=True)


# ── 📊 데이터 로직 API 영역 ──────────────────────────────────


# 🎯 [개조 완료] 타사 데이터 원천 필터링 격리 체계 수립
@app.get("/api/dashboard")
def get_dashboard_data(email: str = Query(...), domain: Optional[str] = Query(None)):
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # 1. 호출한 유저의 회사명 추출
        cursor.execute("SELECT company_name FROM web_users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            return {"status": "success", "count": 0, "data": []}

        company_name = user["company_name"]

        import re
        def _normalize(s: str) -> str:
            s = s.lower().strip()
            s = re.sub(r"[^a-z0-9_]", "_", s)
            s = re.sub(r"_+", "_", s).strip("_")
            return s[:50]

        # 타사 위키피디아 간섭 방어용 회사 접두사 규격 생성
        company_prefix = f"{_normalize(company_name)}_"

        if domain:
            # 2-A. 특정 부서 도메인이 찍혀 넘어왔다면 해당 파이프라인만 정밀 조제 (예: asung_ecommerce)
            exact_target = f"{company_prefix}{_normalize(domain)}"
            query = """
                SELECT window_start, domain_name, total_ingested_rows AS total_cnt, 
                       passed_rows AS clean_cnt, quarantined_rows AS error_cnt, data_purity_rate AS purity_rate 
                FROM web_main_dashboard
                WHERE domain_name = %s
                ORDER BY window_start DESC;
            """
            cursor.execute(query, (exact_target,))
        else:
            # 2-B. 기본 로딩 시 내 소유의 파이프라인만 LIKE 스캔으로 안전 격리 로드
            query = """
                SELECT window_start, domain_name, total_ingested_rows AS total_cnt, 
                       passed_rows AS clean_cnt, quarantined_rows AS error_cnt, data_purity_rate AS purity_rate 
                FROM web_main_dashboard
                WHERE domain_name LIKE %s
                ORDER BY window_start DESC;
            """
            cursor.execute(query, (company_prefix + "%",))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return {"status": "success", "count": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 연결 실패: {str(e)}")


class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    company_name: str


@app.post("/api/login")
def login_user(login_info: LoginRequest):
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, email, password_hash, company_name, domain_name"
            " FROM web_users WHERE email = %s;",
            (login_info.email,),
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user or login_info.password != user["password_hash"]:
            raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

        return {
            "status": "success",
            "message": "로그인 성공",
            "user_info": {"company_name": user["company_name"], "domain_name": user["domain_name"]},
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


# ── 🔧 규칙 관리 API 영역 ────────────────────────────────────────


@app.get("/api/rules/versions")
def list_versions(email: str = Query(...), domain: str = Query(...)):
    verify_domain_ownership(email, domain)
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM rule_versions WHERE domain = %s", (domain,))
        if cur.fetchone()["cnt"] == 0:
            cur.close()
            conn.close()
            r = get_redis_client()
            raw = r.get(f"gx_rules:{domain.lower()}")
            if raw:
                save_new_version(
                    domain,
                    json.loads(raw),
                    "system",
                    "초기 AI 생성 규칙 (자동 마이그레이션)",
                    activate=True,
                )

        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, version_num, created_at, created_by, note, is_active
            FROM rule_versions WHERE domain = %s ORDER BY version_num DESC
        """,
            (domain,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"status": "success", "versions": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"버전 목록 조회 실패: {str(e)}")


@app.get("/api/rules/version/{version_id}")
def get_version_rules(version_id: int, email: str = Query(...), domain: str = Query(...)):
    verify_domain_ownership(email, domain)
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rule_versions WHERE id = %s AND domain = %s", (version_id, domain)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="버전을 찾을 수 없습니다.")
        rules = json.loads(row["rules_json"])
        return {"status": "success", "version": dict(row), "rules": rules}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"버전 조회 실패: {str(e)}")


class ActivateVersionRequest(BaseModel):
    email: str
    domain: str
    version_id: int


@app.post("/api/rules/activate")
def activate_version(body: ActivateVersionRequest):
    verify_domain_ownership(body.email, body.domain)
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rule_versions WHERE id = %s AND domain = %s",
            (body.version_id, body.domain),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="버전을 찾을 수 없습니다.")
        rules = json.loads(row["rules_json"])
        cur.execute("UPDATE rule_versions SET is_active = FALSE WHERE domain = %s", (body.domain,))
        cur.execute("UPDATE rule_versions SET is_active = TRUE WHERE id = %s", (body.version_id,))
        conn.commit()
        cur.close()
        conn.close()
        r = get_redis_client()
        rules["_version"] = row["version_num"]
        r.set(f"gx_rules:{body.domain.lower()}", json.dumps(rules, ensure_ascii=False))
        return {"status": "success", "activated_version": row["version_num"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"버전 활성화 실패: {str(e)}")


class SaveRulesRequest(BaseModel):
    email: str
    domain: str
    rules: dict
    note: Optional[str] = "사용자 편집"


@app.post("/api/rules/save")
def save_rules(body: SaveRulesRequest):
    verify_domain_ownership(body.email, body.domain)
    try:
        version_num = save_new_version(
            body.domain, body.rules, body.email, body.note or "사용자 편집", activate=True
        )
        return {"status": "success", "version_num": version_num}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"규칙 저장 실패: {str(e)}")


@app.get("/api/domains")
def get_user_domains(email: str = Query(...)):
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ds.bronze_folder, ds.source_name, ds.data_source_type
            FROM data_sources ds
            JOIN web_users wu ON ds.user_id = wu.user_id
            WHERE wu.email = %s AND ds.status = 'active'
            ORDER BY ds.created_at
        """,
            (email,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "success", "domains": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"도메인 목록 조회 실패: {str(e)}")


@app.get("/api/rules")
def get_rules(email: str = Query(...), domain: str = Query(...)):
    verify_domain_ownership(email, domain)
    try:
        r = get_redis_client()
        raw = r.get(f"gx_rules:{domain.lower()}")
        if not raw:
            return {"status": "success", "domain": domain, "rules": None}
        rules = json.loads(raw)
        for exp in rules.get("expectations", []):
            exp.setdefault("enabled", True)
        for rule in rules.get("anomaly_rules", []):
            rule.setdefault("enabled", True)
        return {"status": "success", "domain": domain, "rules": rules}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"규칙 조회 실패: {str(e)}")


class ToggleRequest(BaseModel):
    email: str
    domain: str
    rule_type: str
    rule_index: int
    enabled: bool


@app.patch("/api/rules/toggle")
def toggle_rule(body: ToggleRequest):
    if body.rule_type not in ("expectations", "anomaly_rules"):
        raise HTTPException(
            status_code=400, detail="rule_type은 'expectations' 또는 'anomaly_rules'여야 합니다."
        )
    verify_domain_ownership(body.email, body.domain)
    try:
        r = get_redis_client()
        raw = r.get(f"gx_rules:{body.domain.lower()}")
        if not raw:
            raise HTTPException(status_code=404, detail="해당 도메인의 규칙이 존재하지 않습니다.")
        rules = json.loads(raw)
        rule_list = rules.get(body.rule_type, [])
        if body.rule_index < 0 or body.rule_index >= len(rule_list):
            raise HTTPException(status_code=400, detail="유효하지 않은 규칙 인덱스입니다.")
        rule_list[body.rule_index]["enabled"] = body.enabled
        action = "활성화" if body.enabled else "비활성화"
        col = rule_list[body.rule_index].get("column") or rule_list[body.rule_index].get("name", "")
        save_new_version(body.domain, rules, body.email, f"{col} 규칙 {action}", activate=True)
        return {
            "status": "success",
            "domain": body.domain,
            "rule_type": body.rule_type,
            "rule_index": body.rule_index,
            "enabled": body.enabled,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"규칙 토글 실패: {str(e)}")


# ── 🛡️ 격리(Quarantine) 위반 데이터 사유 수정 및 제어 API 영역 ────────


@app.post("/api/quarantine/{domain}/delete")
def api_delete_quarantine(domain: str, req: QuarantineActionRequest):
    try:
        container_client = blob_service_client.get_container_client("quarantine")

        if req.row_ids:
            df = _get_blob_df("quarantine", f"{domain}/")
            if not df.empty and "_row_hash" in df.columns:
                df_remain = df[~df["_row_hash"].isin(req.row_ids)]
                _write_blob_df("quarantine", f"{domain}/quarantine_data.parquet", df_remain)
            target_str = f"{len(req.row_ids)}건 행"
        else:
            blob_list = container_client.list_blobs(name_starts_with=f"{domain}/")
            for blob in blob_list:
                container_client.delete_blob(blob.name)
            target_str = "전체 데이터"

        _log_quarantine_action(domain, req.row_ids, "delete", req.reason)

        return {
            "status": "success",
            "message": f"[{domain}] {target_str} 폐기 완료 (조치사유: {req.reason})",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"격리 데이터 폐기 실패: {str(e)}")


@app.post("/api/quarantine/{domain}/approve")
def api_approve_to_master(domain: str, req: QuarantineActionRequest):
    META_COLS = [
        "__quarantine_reason",
        "_ingest_ts",
        "_source_type",
        "_platform",
        "_company",
        "_domain",
        "_row_hash",
        "_quarantine_ts",
        "_processed_at",
        "_run_id",
        "_epoch_id",
    ]

    try:
        df_q = _get_blob_df("quarantine", f"{domain}/")
        if df_q.empty:
            raise HTTPException(
                status_code=404, detail="처리할 대상 격리 데이터 파티션이 비어있습니다."
            )

        df_approved = df_q[df_q["_row_hash"].isin(req.row_ids)] if req.row_ids else df_q

        drop_cols = [c for c in META_COLS if c in df_approved.columns]
        df_approved = df_approved.drop(columns=drop_cols)

        try:
            df_silver = _get_blob_df("silver", f"{domain}/")
            if not df_silver.empty:
                drop_s = [c for c in META_COLS if c in df_silver.columns]
                df_silver = df_silver.drop(columns=drop_s)
        except Exception:
            df_silver = pd.DataFrame()

        df_master = (
            pd.concat([df_silver, df_approved], ignore_index=True)
            if not df_silver.empty
            else df_approved
        )
        df_master["_merged_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_filename = f"{domain}/master_report_{timestamp}.parquet"
        _write_blob_df("master", blob_filename, df_master)

        _log_quarantine_action(domain, req.row_ids, "approve", req.reason)

        if req.row_ids:
            df_remain = df_q[~df_q["_row_hash"].isin(req.row_ids)]
            _write_blob_df("quarantine", f"{domain}/quarantine_data.parquet", df_remain)
        else:
            container_client = blob_service_client.get_container_client("quarantine")
            blob_list = container_client.list_blobs(name_starts_with=f"{domain}/")
            for blob in blob_list:
                container_client.delete_blob(blob.name)

        return {
            "status": "success",
            "message": f"[{domain}] 격리 데이터 마스터 컨테이너 정상 갱신 및 결합 승인 완료",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마스터 강제 병합 및 업데이트 실패: {str(e)}")


# ── 💾 마스터(Master) 컨테이너 정형화 리포트 다운로드 API 영역 ───────


@app.get("/api/download/{domain}")
def download_master_csv(domain: str):
    try:
        df_master = _get_blob_df("master", f"{domain}/")

        if df_master.empty:
            raise HTTPException(
                status_code=404,
                detail=f"[{domain}] 마스터 컨테이너 영역에 최종 정형 보고서가 존재하지 않습니다.",
            )

        csv_buffer = io.StringIO()
        df_master.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        csv_buffer.seek(0)

        return StreamingResponse(
            io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig")),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={domain}_final_master_report.csv"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"다운로드 파일 연산 실패: {str(e)}")


# ── 🚀 파일 업로드 및 카프카 적재 API 영역 ─────────────────────


@app.post("/api/upload")
async def upload_batch_file(
    email: str = Form(...), domain: str = Form(...), file: UploadFile = File(...)
):
    filename = file.filename
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="CSV 또는 Excel 파일만 업로드 가능합니다.")

    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT user_id, company_name FROM web_users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사용자 조회 실패: {str(e)}")

    if not user:
        raise HTTPException(status_code=401, detail="등록되지 않은 이메일입니다.")

    user_id = user["user_id"]
    company_name = user["company_name"]

    import re

    def _normalize(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9_]", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s[:50]

    bronze_folder = f"{_normalize(company_name)}_{_normalize(domain)}"

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        cur.execute(
            "SELECT 1 FROM data_sources WHERE user_id = %s AND bronze_folder = %s",
            (user_id, bronze_folder),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO data_sources (user_id, bronze_folder, source_name, status)
                VALUES (%s, %s, %s, 'active')
                """,
                (user_id, bronze_folder, bronze_folder),
            )
            
        cur.execute(
            "UPDATE web_users SET domain_name = %s WHERE user_id = %s",
            (domain, user_id)
        )
        
        conn.commit()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"도메인 메타 정보 동기화 실패: {str(e)}")

    temp_file_path = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임시 파일 저장 실패: {str(e)}")

    try:
        result = process_batch_file(company=company_name, domain=domain, file_path=temp_file_path)

        if result.get("status") == "success":
            return {
                "status": "success",
                "message": (
                    f"성공적으로 {result['sent']:,}행이 "
                    f"카프카 토픽({result['topic']})으로 전송되었습니다."
                ),
                "details": result,
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("reason", "배치 적재 실패"))

    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"배치 파이프라인 연동 중 예외 발생: {str(e)}")
    

@app.post("/api/register")
def register_user(req: RegisterRequest):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT 1 FROM web_users WHERE email = %s;", (req.email,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")
        
        insert_user_query = """
            INSERT INTO web_users (email, password_hash, company_name, domain_name)
            VALUES (%s, %s, %s, 'default') RETURNING user_id;
        """
        cur.execute(insert_user_query, (req.email, req.password, req.company_name))
        
        conn.commit()
        return {
            "status": "success", 
            "message": "회원가입 완료"
        }
        
    except psycopg2.Error as db_err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"DB 적재 실패: {str(db_err)}")
    except HTTPException as he:
        conn.rollback()
        raise he
    finally:
        cur.close()
        conn.close()


# ── 🌐 프론트엔드 정적 페이지 서빙 영역 ────────────────────────


@app.get("/")
@app.get("/index.html")
@app.get("/index")
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


@app.get("/rules.html")
@app.get("/rules")
def read_rules():
    return FileResponse(os.path.join(FRONTEND_DIR, "rules.html"))


@app.get("/app.js")
def read_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))


@app.get("/register.html")
@app.get("/register")
def read_register():
    return FileResponse(os.path.join(FRONTEND_DIR, "register.html"))