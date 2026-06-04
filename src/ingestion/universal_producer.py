"""
DataSentinel — Universal Producer
==================================
역할:
  1. tenant_manager로 Kafka 토픽 자동 생성
  2. 각 소스에서 원본 데이터 전체를 수집
  3. Kafka 토픽으로 전송 (Databricks가 읽어서 Bronze 적재)

핵심 변경사항:
  - 원본 데이터 전체 보존 (필드 선택 없이 100% 전송)
  - SSE 연결 끊기면 자동 재연결
  - DataSentinel 메타데이터만 추가 (_ingest_ts 등)

새 소스 추가: SOURCES 리스트에 항목 추가만 하면 됨
실행: python src/ingestion/universal_producer.py
중단: Ctrl+C
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(__file__))
from tenant_manager import TenantManager  # noqa: E402

try:
    from kafka import KafkaProducer
    from kafka.errors import NoBrokersAvailable

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# ── Kafka 접속 정보 (.env 에서만 읽음) ──────────────────
_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
if not _bootstrap:
    raise EnvironmentError("❌ KAFKA_BOOTSTRAP_SERVERS 환경변수가 없습니다. .env 확인하세요.")

KAFKA_PRODUCER_CONFIG = {
    "bootstrap_servers": _bootstrap.split(","),
    "security_protocol": "SASL_PLAINTEXT",
    "sasl_mechanism": "SCRAM-SHA-256",
    "sasl_plain_username": os.getenv("KAFKA_USERNAME"),
    "sasl_plain_password": os.getenv("KAFKA_PASSWORD"),
    "value_serializer": lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    "acks": "all",
    "retries": 3,
}

# ── 소스 목록 ────────────────────────────────────────────
SOURCES = [
    {
        "company": "Wikipedia",
        "domain": "content",
        "source": "sse",
        "type": "sse",
        "url": "https://stream.wikimedia.org/v2/stream/recentchange",
        "enabled": True,
    },
    # 나중에 추가:
    # {
    #     "company": "CoinPaprika",
    #     "domain":  "finance",
    #     "source":  "api",
    #     "type":    "rest_api",
    #     "url":     "https://api.coinpaprika.com/v1/tickers",
    #     "enabled": False,
    # },
    # {
    #     "company": "NHIS",
    #     "domain":  "healthcare",
    #     "source":  "batch",
    #     "type":    "batch",
    #     "url":     "",
    #     "enabled": False,
    # },
]


# ── SSE 파서 — 원본 전체 보존 ───────────────────────────
def parse_sse_event(raw_line: bytes) -> dict | None:
    """
    원본 데이터를 100% 그대로 보존.
    DataSentinel 메타데이터(_)만 추가.

    Bronze = 원본 전체 + DataSentinel 메타데이터
    필드 선택·수정 없음 → 품질 검증 플랫폼 원칙
    """
    try:
        if not raw_line or not raw_line.startswith(b"data:"):
            return None

        data = json.loads(raw_line[5:].strip())

        if data.get("type") != "edit":
            return None

        event = data.copy()

        event["_ingest_ts"] = datetime.utcnow().isoformat() + "Z"
        event["_source_type"] = "sse"
        event["_platform"] = "datasentinel"

        length = data.get("length") or {}
        event["_bytes_changed"] = (length.get("new") or 0) - (length.get("old") or 0)

        return event

    except Exception:
        return None


# ── SSE 수집기 — 자동 재연결 포함 ───────────────────────
def collect_sse(source_cfg: dict, topic: str, producer):
    """
    SSE 방식 수집.
    연결 끊기면 5초 후 자동 재연결.
    """
    company = source_cfg["company"]
    url = source_cfg["url"]
    sent = 0
    reconnect = 0
    MAX_RECONNECT = 10

    while reconnect <= MAX_RECONNECT:
        try:
            if reconnect > 0:
                print(f"  [{company}] 재연결 시도 {reconnect}/{MAX_RECONNECT}...")
                time.sleep(5)

            print(f"  [{company}] SSE 연결 중... ({url})")

            resp = requests.get(
                url,
                headers={"User-Agent": "DataSentinel/1.0"},
                stream=True,
                timeout=60,
            )

            for raw_line in resp.iter_lines():
                event = parse_sse_event(raw_line)
                if not event:
                    continue

                try:
                    producer.send(topic, value=event).get(timeout=5)
                    sent += 1
                    reconnect = 0

                    if sent % 10 == 0:
                        null_flag = " ⚠️ NULL" if not event.get("user") else ""
                        print(
                            f"  [{company}][{sent:05d}] "
                            f"{event.get('wiki', ''):<10} | "
                            f"{str(event.get('title', ''))[:25]:<25} | "
                            f"{str(event.get('user') or 'NULL')[:10]:<10} | "
                            f"{event.get('_bytes_changed', 0):+6d}bytes"
                            f"{null_flag}"
                        )

                except Exception as e:
                    print(f"  [{company}] 전송 실패: {e}")

        except Exception as e:
            print(f"  [{company}] 연결 오류: {e}")
            reconnect += 1

    print(f"  [{company}] 최대 재연결 횟수 초과. 중단됨.")


# ── REST API 수집기 ──────────────────────────────────────
def collect_rest_api(source_cfg: dict, topic: str, producer):
    """REST API 방식 (CoinPaprika 등). 추후 구현."""
    print(f"  [{source_cfg['company']}] REST API 수집 (미구현)")


# ── 배치 수집기 ─────────────────────────────────────────
def collect_batch(source_cfg: dict, topic: str, producer):
    """배치 방식 (CSV 파일 등). 추후 구현."""
    print(f"  [{source_cfg['company']}] 배치 수집 (미구현)")


# 소스 타입 → 수집 함수 매핑
COLLECTOR_MAP = {
    "sse": collect_sse,
    "rest_api": collect_rest_api,
    "batch": collect_batch,
}


# ── 메인 ─────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  DataSentinel — Universal Producer v2")
    print("  원본 데이터 100% 보존 + 자동 재연결")
    print("=" * 55)

    print("\n[1/3] 토픽 확인 및 생성...")
    tm = TenantManager()
    topics = {}

    for src in SOURCES:
        if not src.get("enabled"):
            continue
        tenant = tm.register_tenant(
            company=src["company"],
            domain=src["domain"],
            source=src["source"],
        )
        topics[src["company"]] = tenant.topic_name

    print("\n생성된 토픽:")
    for company, topic in topics.items():
        print(f"  {company} → {topic}")

    print("\n[2/3] Kafka Producer 초기화...")
    if not KAFKA_AVAILABLE:
        print("  ❌ kafka-python 미설치")
        return

    try:
        producer = KafkaProducer(**KAFKA_PRODUCER_CONFIG)
        print("  ✅ 연결 성공")
    except NoBrokersAvailable:
        print("  ❌ Kafka 브로커 연결 실패")
        return

    print("\n[3/3] 수집 시작...")
    print("-" * 55)

    threads = []
    for src in SOURCES:
        if not src.get("enabled"):
            continue
        topic = topics[src["company"]]
        collector = COLLECTOR_MAP.get(src["type"], collect_sse)

        t = threading.Thread(
            target=collector,
            args=(src, topic, producer),
            daemon=True,
            name=src["company"],
        )
        threads.append(t)
        t.start()
        print(f"  ✅ {src['company']} 수집 시작 → {topic}")

    print("\n  원본 전체 보존 중 (필드 선택 없음)")
    print("  Ctrl+C 로 중단\n")

    try:
        while True:
            time.sleep(60)
            alive = [t for t in threads if t.is_alive()]
            print(f"  [상태] 활성 스레드: {len(alive)}/{len(threads)}")
    except KeyboardInterrupt:
        print("\n\n중단됨")
        print("\n  B팀 공유 토픽명:")
        for company, topic in topics.items():
            print(f"    {company}: {topic}")
    finally:
        producer.flush()
        producer.close()
        print("\n  완료")


if __name__ == "__main__":
    main()
