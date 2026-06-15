"""
DataSentinel — Batch Producer
==============================
역할:
  웹사이트에서 업로드된 CSV/Excel 파일을
  Kafka를 통해 Bronze Delta에 적재

제한:
  - 1GB 미만만 처리
  - 지원 형식: CSV, Excel(.xlsx, .xls)
  - Excel은 200MB 미만만 처리
  - 100MB 이상 CSV는 청크(10,000행) 분할 처리

호출 방법 (FastAPI에서):
  from batch_producer import process_batch_file
  result = process_batch_file(
      company="wikipedia",
      domain="content",
      file_path="/tmp/data.csv"
  )

Bronze 폴더명 규칙: {company}_{domain}  (예: wikipedia_content)
Kafka 토픽 규칙:    {company}.{domain}  (예: wikipedia.content)

반환:
  {"status": "success", "sent": N, "failed": N,
   "topic": "...", "bronze_folder": "..."}
  {"status": "error", "reason": "..."}
"""

import json
import os
import sys
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(__file__))
from tenant_manager import TenantManager

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# ── Kafka 접속 정보 (.env 에서만 읽음) ──────────────────
_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
if not _bootstrap:
    raise EnvironmentError("❌ KAFKA_BOOTSTRAP_SERVERS 환경변수가 없습니다. .env 확인하세요.")

KAFKA_PRODUCER_CONFIG = {
    "bootstrap_servers":   _bootstrap.split(","),
    "security_protocol":   "SASL_PLAINTEXT",
    "sasl_mechanism":      "SCRAM-SHA-256",
    "sasl_plain_username": os.getenv("KAFKA_USERNAME"),
    "sasl_plain_password": os.getenv("KAFKA_PASSWORD"),
    "value_serializer":    lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    "acks":    "all",
    "retries": 3,
}

# ── 파일 크기 제한 ───────────────────────────────────────
LIMIT_MB       = 1024  # 1GB — 초과 시 거부
EXCEL_LIMIT_MB = 200   # Excel 200MB 초과 시 CSV 변환 요구
CHUNK_SIZE     = 10_000  # 청크 처리 행 수


# ── Kafka 연결 ───────────────────────────────────────────
def _create_producer() -> "KafkaProducer | None":
    """Kafka Producer 생성. 실패 시 None 반환."""
    if not KAFKA_AVAILABLE:
        print("  ❌ kafka-python 미설치")
        return None
    try:
        producer = KafkaProducer(**KAFKA_PRODUCER_CONFIG)
        print("  ✅ Kafka 연결 성공")
        return producer
    except Exception as e:
        print(f"  ❌ Kafka 연결 실패: {e}")
        return None


# ── 파일 읽기 ────────────────────────────────────────────
def _read_file(file_path: str, file_size_mb: float):
    """
    파일 형식 및 크기에 따라 청크 이터레이터 반환.
    실패 시 None 반환.
    """
    try:
        if file_path.endswith(".csv"):
            if file_size_mb >= 100:
                print(f"  100MB 이상 → 청크 처리 ({CHUNK_SIZE:,}행 단위)")
                return pd.read_csv(file_path, chunksize=CHUNK_SIZE)
            return [pd.read_csv(file_path)]

        elif file_path.endswith((".xlsx", ".xls")):
            if file_size_mb >= EXCEL_LIMIT_MB:
                print(f"  ❌ Excel {file_size_mb:.0f}MB 초과 → CSV로 변환 후 재업로드 필요")
                return None
            return [pd.read_excel(file_path)]

        else:
            print(f"  ❌ 지원 형식: CSV, Excel(.xlsx, .xls)만 가능")
            return None

    except Exception as e:
        print(f"  ❌ 파일 읽기 실패: {e}")
        return None


# ── 메인 함수 (FastAPI에서 호출) ─────────────────────────
def process_batch_file(
    company: str,
    domain: str,
    file_path: str,
) -> dict:
    """
    웹 업로드 파일 → Kafka → Bronze 적재

    Args:
        company:   회사명 (예: wikipedia)
        domain:    도메인명 (예: content)  ← kafka2bronze의 TENANT_NAME 규칙과 동일
        file_path:   로컬 임시 파일 경로

    Returns:
        성공: {"status": "success", "sent": N, "failed": N,
               "topic": "...", "bronze_folder": "..."}
        실패: {"status": "error", "reason": "..."}
    """
    print(f"\n[배치 처리 시작] {company} / {domain}")

    # ── 1. 파일 존재 확인 ────────────────────────────────
    if not os.path.exists(file_path):
        return {"status": "error", "reason": f"파일 없음: {file_path}"}

    # ── 2. 파일 크기 검증 ────────────────────────────────
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"  파일 크기: {file_size_mb:.1f}MB")

    if file_size_mb >= LIMIT_MB:
        reason = f"1GB 초과 ({file_size_mb:.0f}MB) — 1GB 미만 파일만 처리 가능"
        print(f"  ❌ {reason}")
        return {"status": "error", "reason": reason}

    # ── 3. 파일 읽기 ─────────────────────────────────────
    chunks = _read_file(file_path, file_size_mb)
    if chunks is None:
        return {"status": "error", "reason": "파일 읽기 실패 또는 지원하지 않는 형식"}

    # ── 4. Kafka 토픽 자동 생성 ──────────────────────────
    tm     = TenantManager()
    tenant = tm.register_tenant(company, domain, "batch")
    topic  = tenant.topic_name
    bronze_folder = f"{tm._normalize(company)}_{tm._normalize(domain)}"
    print(f"  토픽: {topic}")
    print(f"  Bronze 폴더: {bronze_folder}")

    # ── 5. Kafka 연결 ─────────────────────────────────────
    producer = _create_producer()
    if not producer:
        return {"status": "error", "reason": "Kafka 연결 실패"}

    # ── 6. 행 단위 전송 ──────────────────────────────────
    sent   = 0
    failed = 0

    try:
        for chunk in chunks:
            for _, row in chunk.iterrows():
                try:
                    # 원본 데이터 100% 보존 + 메타데이터만 추가
                    event = row.where(pd.notna(row), None).to_dict()
                    event["_ingest_ts"]   = datetime.utcnow().isoformat() + "Z"
                    event["_source_type"] = "batch"
                    event["_platform"]    = "datasentinel"
                    event["_company"]     = company
                    event["_domain"] = domain

                    producer.send(topic, value=event)
                    sent += 1

                    if sent % 1_000 == 0:
                        print(f"  전송 중: {sent:,}행")

                except Exception as e:
                    failed += 1
                    if failed <= 5:
                        print(f"  ⚠️ 행 전송 실패: {e}")

    finally:
        producer.flush()
        producer.close()

        # ── 7. 임시 파일 삭제 (Blob은 수명 주기 규칙으로 1일 후 자동 삭제)
        try:
            os.remove(file_path)
            print(f"  임시 파일 삭제 완료: {file_path}")
        except Exception:
            pass

    print(f"  완료 | 성공: {sent:,}행 | 실패: {failed}행")

    return {
        "status":        "success",
        "sent":          sent,
        "failed":        failed,
        "topic":         topic,
        "bronze_folder": bronze_folder,
    }