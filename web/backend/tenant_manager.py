"""
DataSentinel — Tenant Manager
토픽 이름 규칙 정의 + Kafka 토픽 자동 생성

네이밍 규칙: {회사명}.{도메인}.{소스}.raw
예시: wikipedia.content.sse.raw
     coinpaprika.finance.api.raw
     samsung.healthcare.csv.raw

나중에 웹 UI 연결 포인트:
    FastAPI → tm.register_tenant(company, domain, source)
"""

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

try:
    from kafka import KafkaAdminClient
    from kafka.admin import NewTopic
    from kafka.errors import TopicAlreadyExistsError

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    print("⚠️  kafka-python 없음 — 시뮬레이션 모드")

# ── Kafka 접속 정보 (.env 에서만 읽음) ──────────────────
_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
if not _bootstrap:
    raise EnvironmentError("❌ KAFKA_BOOTSTRAP_SERVERS 환경변수가 없습니다. .env 확인하세요.")

KAFKA_CONFIG = {
    "bootstrap_servers": _bootstrap.split(","),
    "security_protocol": "SASL_PLAINTEXT",
    "sasl_mechanism": "SCRAM-SHA-256",
    "sasl_plain_username": os.getenv("KAFKA_USERNAME"),
    "sasl_plain_password": os.getenv("KAFKA_PASSWORD"),
}

# 도메인별 파티션 수
DOMAIN_PARTITIONS = {
    "finance": 6,
    "ecommerce": 6,
    "iot": 6,
    "content": 3,
    "healthcare": 3,
    "logistics": 3,
    "test": 3,
    "unknown": 3,
}


@dataclass
class TenantInfo:
    company_id: str
    company_name: str
    domain: str
    source: str
    topic_name: str
    partitions: int
    created_at: str
    status: str

    def to_dict(self):
        return asdict(self)


class TenantManager:
    def __init__(self):
        self.registry: dict[str, TenantInfo] = {}
        self._load_registry()

    def _normalize(self, s: str) -> str:
        """특수문자·대문자·공백 → 소문자·언더스코어"""
        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9_]", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s[:50]

    def _make_topic_name(self, company: str, domain: str, source: str) -> str:
        """
        토픽 네이밍 규칙: {회사명}.{도메인}.{소스}.raw

        Wikipedia + content + sse  → wikipedia.content.sse.raw
        HyundaiMotor + finance + api → hyundaimotor.finance.api.raw
        """
        return f"{self._normalize(company)}.{self._normalize(domain)}.{self._normalize(source)}.raw"

    def register_tenant(
        self,
        company: str,
        domain: str,
        source: str,
        partitions: Optional[int] = None,
    ) -> TenantInfo:
        """
        ┌──────────────────────────────────────────┐
        │  WEB 연결 포인트 (나중에 여기로 연결)    │
        │                                          │
        │  지금: universal_producer.py에서 호출    │
        │  나중: FastAPI 엔드포인트에서 호출       │
        │                                          │
        │  POST /api/v1/tenant/register            │
        │  { "company": "HyundaiMotor",            │
        │    "domain": "finance",                  │
        │    "source": "api" }                     │
        │  → 이 함수 호출 → 토픽 자동 생성        │
        └──────────────────────────────────────────┘
        """
        topic_name = self._make_topic_name(company, domain, source)
        num_parts = partitions or DOMAIN_PARTITIONS.get(domain.lower(), 3)

        print(f"\n{'=' * 50}")
        print(f"  테넌트 등록: {company}")
        print(f"  토픽명:     {topic_name}")
        print(f"  파티션:     {num_parts}개")

        if topic_name in self.registry:
            print("  ✅ 기존 토픽 재사용")
            print(f"{'=' * 50}")
            return self.registry[topic_name]

        status = self._create_kafka_topic(topic_name, num_parts)
        print(f"{'=' * 50}")

        tenant = TenantInfo(
            company_id=self._normalize(company),
            company_name=company,
            domain=domain.lower(),
            source=source.lower(),
            topic_name=topic_name,
            partitions=num_parts,
            created_at=datetime.now().isoformat(),
            status=status,
        )

        self.registry[topic_name] = tenant
        self._save_registry()
        return tenant

    def _create_kafka_topic(self, topic_name: str, partitions: int) -> str:
        if not KAFKA_AVAILABLE:
            print(f"  [시뮬레이션] 생성: {topic_name}")
            return "simulated"
        try:
            admin = KafkaAdminClient(**KAFKA_CONFIG)
            existing = admin.list_topics()

            if topic_name in existing:
                print(f"  ✅ 이미 존재: {topic_name}")
                admin.close()
                return "exists"

            admin.create_topics(
                [
                    NewTopic(
                        name=topic_name,
                        num_partitions=partitions,
                        replication_factor=2,
                        topic_configs={"retention.ms": "86400000"},
                    )
                ]
            )
            admin.close()
            print(f"  ✅ 생성 완료: {topic_name}")
            return "created"

        except TopicAlreadyExistsError:
            return "exists"
        except Exception as e:
            print(f"  ❌ 실패: {e}")
            return "failed"

    def get_topic(self, company: str, domain: str, source: str) -> str:
        """토픽명만 빠르게 가져오기"""
        return self._make_topic_name(company, domain, source)

    def list_tenants(self):
        print(f"\n등록된 테넌트 ({len(self.registry)}개):")
        for _, info in self.registry.items():
            icon = "✅" if "fail" not in info.status else "❌"
            print(f"  {icon} {info.topic_name:<40} ({info.company_name})")

    def _save_registry(self):
        path = os.path.join(os.path.dirname(__file__), "tenant_registry.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {k: v.to_dict() for k, v in self.registry.items()}, f, ensure_ascii=False, indent=2
            )

    def _load_registry(self):
        path = os.path.join(os.path.dirname(__file__), "tenant_registry.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    self.registry[k] = TenantInfo(**v)
            print(f"  기존 테넌트 {len(self.registry)}개 로드됨")
        except FileNotFoundError:
            pass
