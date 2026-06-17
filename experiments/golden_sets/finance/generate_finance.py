"""
금융 도메인 골든셋 생성 스크립트
- golden_set_finance_v1.jsonl        : 명확한 규칙 위반 케이스 (수동 작성 고정)
- golden_set_finance_anomaly_v1.jsonl: 이상치 탐지 규칙 케이스 (실제 데이터 통계 기반)

실행:
    uv run python experiments/golden_sets/generate_finance.py
"""

import json
import os

import kagglehub
import numpy as np
import pandas as pd

# ── 경로 설정 ──────────────────────────────────────────────
OUT_DIR = os.path.dirname(__file__)
ANOMALY_OUT = os.path.join(OUT_DIR, "golden_set_finance_anomaly_v1.jsonl")

# ── Step 1: 데이터 다운로드 ────────────────────────────────
print("[1/3] Kaggle 데이터셋 다운로드 중...")
path = kagglehub.dataset_download("alfarisbachmid/dirty-financial-transactions-dataset")
print(f"  Path: {path}")

df = pd.read_csv(os.path.join(path, "dirty_financial_transactions.csv"))
print(f"  행 수: {len(df):,} | 컬럼: {list(df.columns)}")

# 더티 데이터 전처리: 수치 컬럼 강제 변환 (비정상값 → NaN)
df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
p_null = df["Price"].isnull().sum()
q_null = df["Quantity"].isnull().sum()
print(f"  Price null: {p_null:,} | Quantity null: {q_null:,}")

# ── Step 2: 실제 통계 계산 ─────────────────────────────────
print("\n[2/3] 통계 계산 중...")

# R9: Quantity IQR
q1_qty = float(df["Quantity"].quantile(0.25))
q3_qty = float(df["Quantity"].quantile(0.75))
iqr_qty = q3_qty - q1_qty
lower_qty = round(q1_qty - 1.5 * iqr_qty, 4)
upper_qty = round(q3_qty + 1.5 * iqr_qty, 4)
print(f"  Quantity IQR: Q1={q1_qty}, Q3={q3_qty}, IQR={iqr_qty}")
print(f"  Quantity bounds: [{lower_qty}, {upper_qty}]")

# R10: Price Z-score
mean_price = round(float(df["Price"].mean()), 2)
std_price = round(float(df["Price"].std()), 2)
print(f"  Price Z-score: mean={mean_price}, std={std_price}")

# R11: Transaction_Status frequency
status_counts = df["Transaction_Status"].value_counts().to_dict()
status_counts = {k: int(v) for k, v in status_counts.items()}
mean_status = round(float(np.mean(list(status_counts.values()))), 2)
std_status = round(float(np.std(list(status_counts.values()))), 2)
print(f"  Status counts: {status_counts}")
print(f"  Status freq: mean={mean_status}, std={std_status}")

# R11: Payment_Method frequency
payment_counts = df["Payment_Method"].value_counts().to_dict()
payment_counts = {k: int(v) for k, v in payment_counts.items()}
mean_payment = round(float(np.mean(list(payment_counts.values()))), 2)
std_payment = round(float(np.std(list(payment_counts.values()))), 2)
print(f"  Payment counts: {payment_counts}")

# ── Step 3: 이상치 골든셋 생성 ────────────────────────────
print("\n[3/3] golden_set_finance_anomaly_v1.jsonl 생성 중...")

golden_anomaly = [
    # R9: Quantity IQR — 규칙 존재 여부 (실제 통계값)
    {
        "id": "fin_R9_rule_001",
        "input": {
            "domain": "financial_transactions",
            "column": "Quantity",
            "method": "iqr",
            "column_profile": {
                "dtype": "numeric",
                "null_rate": round(float(df["Quantity"].isnull().mean()), 4),
                "mean": round(float(df["Quantity"].mean()), 4),
                "std": round(float(df["Quantity"].std()), 4),
                "min": int(df["Quantity"].min()),
                "max": int(df["Quantity"].max()),
                "Q1": q1_qty,
                "Q3": q3_qty,
                "IQR": round(iqr_qty, 4),
                "lower_bound": lower_qty,
                "upper_bound": upper_qty,
                "threshold": 1.5,
            },
        },
        "expected": {
            "has_anomaly_rule": True,
            "method": "iqr",
            "threshold": 1.5,
            "lower_bound": lower_qty,
            "upper_bound": upper_qty,
        },
        "metadata": {
            "rule_tested": "R9",
            "case_type": "rule_existence",
            "difficulty": "easy",
            "note": "Quantity IQR 이상치 탐지 규칙 존재해야 함 — 실제 데이터 통계 기반",
        },
    },
    # R9: string 타입 → IQR 불가
    {
        "id": "fin_R9_rule_002",
        "input": {
            "domain": "financial_transactions",
            "column": "Quantity",
            "method": "iqr",
            "column_profile": {
                "dtype": "string",
                "null_rate": 0.0,
                "sample": ["2", "3", "5"],
            },
        },
        "expected": {
            "has_anomaly_rule": False,
            "reason": "string 타입 컬럼에는 IQR 적용 불가",
        },
        "metadata": {
            "rule_tested": "R9",
            "case_type": "edge",
            "difficulty": "medium",
            "note": "dtype이 string인 경우 IQR 규칙 생성하면 안 됨",
        },
    },
    # R9: categorical 타입 → IQR 불가
    {
        "id": "fin_R9_rule_003",
        "input": {
            "domain": "financial_transactions",
            "column": "Transaction_Status",
            "method": "iqr",
            "column_profile": {
                "dtype": "categorical",
                "null_rate": 0.0,
                "unique_count": int(df["Transaction_Status"].nunique()),
                "sample": df["Transaction_Status"].dropna().unique().tolist()[:3],
            },
        },
        "expected": {
            "has_anomaly_rule": False,
            "reason": "categorical 컬럼에는 IQR 적용 불가",
        },
        "metadata": {
            "rule_tested": "R9",
            "case_type": "edge",
            "difficulty": "medium",
            "note": "categorical 컬럼에 IQR 규칙 생성하면 안 됨",
        },
    },
    # R10: Price Z-score — 규칙 존재 여부 (실제 통계값)
    {
        "id": "fin_R10_rule_001",
        "input": {
            "domain": "financial_transactions",
            "column": "Price",
            "method": "zscore",
            "column_profile": {
                "dtype": "numeric",
                "null_rate": round(float(df["Price"].isnull().mean()), 4),
                "mean": mean_price,
                "std": std_price,
                "min": round(float(df["Price"].min()), 2),
                "max": round(float(df["Price"].max()), 2),
                "threshold": 3,
            },
        },
        "expected": {
            "has_anomaly_rule": True,
            "method": "zscore",
            "threshold": 3,
            "mean": mean_price,
            "std": std_price,
        },
        "metadata": {
            "rule_tested": "R10",
            "case_type": "rule_existence",
            "difficulty": "easy",
            "note": "Price Z-score 이상치 탐지 규칙 존재해야 함 — 실제 데이터 통계 기반",
        },
    },
    # R10: std=0 → Z-score 불가
    {
        "id": "fin_R10_rule_002",
        "input": {
            "domain": "financial_transactions",
            "column": "Price",
            "method": "zscore",
            "column_profile": {
                "dtype": "numeric",
                "null_rate": 0.0,
                "mean": 42000.0,
                "std": 0.0,
                "min": 42000,
                "max": 42000,
                "sample": [42000, 42000, 42000],
            },
        },
        "expected": {
            "has_anomaly_rule": False,
            "reason": "표준편차 0인 경우 Zscore 계산 불가",
        },
        "metadata": {
            "rule_tested": "R10",
            "case_type": "edge",
            "difficulty": "hard",
            "note": "std=0인 경우 Zscore 규칙 생성하면 안 됨 (division by zero)",
        },
    },
    # R11: Transaction_Status frequency (실제 통계값)
    {
        "id": "fin_R11_rule_001",
        "input": {
            "domain": "financial_transactions",
            "column": "Transaction_Status",
            "method": "frequency",
            "column_profile": {
                "dtype": "categorical",
                "null_rate": round(float(df["Transaction_Status"].isnull().mean()), 4),
                "unique_count": int(df["Transaction_Status"].nunique()),
                "value_counts": status_counts,
                "mean": mean_status,
                "std": std_status,
                "threshold": 3,
            },
        },
        "expected": {
            "has_anomaly_rule": True,
            "method": "frequency",
            "threshold": 3,
        },
        "metadata": {
            "rule_tested": "R11",
            "case_type": "rule_existence",
            "difficulty": "medium",
            "note": "Transaction_Status 빈도 이상치 탐지 규칙 존재해야 함 — 실제 데이터 기반",
        },
    },
    # R11: Payment_Method frequency (실제 통계값)
    {
        "id": "fin_R11_rule_002",
        "input": {
            "domain": "financial_transactions",
            "column": "Payment_Method",
            "method": "frequency",
            "column_profile": {
                "dtype": "categorical",
                "null_rate": round(float(df["Payment_Method"].isnull().mean()), 4),
                "unique_count": int(df["Payment_Method"].nunique()),
                "value_counts": payment_counts,
                "mean": mean_payment,
                "std": std_payment,
                "threshold": 3,
            },
        },
        "expected": {
            "has_anomaly_rule": True,
            "method": "frequency",
            "threshold": 3,
        },
        "metadata": {
            "rule_tested": "R11",
            "case_type": "rule_existence",
            "difficulty": "medium",
            "note": "Payment_Method 빈도 이상치 탐지 규칙 존재해야 함 — 실제 데이터 기반",
        },
    },
]

with open(ANOMALY_OUT, "w", encoding="utf-8") as f:
    for case in golden_anomaly:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")

print(f"  [OK] {ANOMALY_OUT}")
print(f"  총 {len(golden_anomaly)}개 케이스")

print("\n[완료] 골든셋 생성 완료")
print(f"  - {os.path.join(OUT_DIR, 'golden_set_finance_v1.jsonl')} (수동 작성 고정)")
print(f"  - {ANOMALY_OUT} (실제 데이터 통계 기반 갱신)")
