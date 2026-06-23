"""
이커머스(UCI Online Retail II) 골든셋 생성기 v2
=================================================
민규님 evaluate_golden_set.py 스키마에 맞춰 두 파일을 생성한다.

  1) golden_set_ec_online_retail_v1.jsonl          (일반 규칙, row 기반, binary)
  2) golden_set_ec_online_retail_anomaly_v1.jsonl  (이상치 규칙, column×method 기반)

핵심:
  - 일반: evaluate_golden_set.check_row_against_rules 가 채점 가능한 규칙만
    (not_null / be_between(min) / regex / in_set). be_unique는 스킵되므로 중복 케이스 제외.
    조건부(취소시 음수 허용)·미래날짜는 GE 어휘로 표현 불가 → 제외.
  - 이상치: "(컬럼, 방법) 규칙을 AI가 생성했어야 하나?" 를 평가.
    string/categorical 컬럼에 zscore/iqr는 생성 금지(expected=False) → 오답 유도 케이스 포함.

사용법:
    python generate_ec_goldenset_v2.py
    (CSV_PATH 를 네 로컬 경로로 맞춰)
"""

import json
import math
import os
from collections import Counter

import pandas as pd

# ── 설정 (여기만 수정) ─────────────────────────────────────
CSV_PATH = r"C:\Users\EL048\Desktop\online retail 2 uci\online_retail_II.csv"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
GENERAL_OUT = os.path.join(OUT_DIR, "golden_set_ec_online_retail_v1.jsonl")
ANOMALY_OUT = os.path.join(OUT_DIR, "golden_set_ec_online_retail_anomaly_v1.jsonl")
SEED = 42
COLS = [
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
]
NONPROD = {
    "POST",
    "DOT",
    "M",
    "C2",
    "BANK CHARGES",
    "AMAZONFEE",
    "CRUK",
    "S",
    "B",
    "D",
    "ADJUST",
    "GIFT",
    "PADS",
}
# ──────────────────────────────────────────────────────────


def detect_column_type(series):
    """run_eval.py auto_profile 과 동일 로직 (dtype 라벨 일치)."""
    non_null = series.dropna()
    if non_null.empty:
        return "unknown"
    if pd.api.types.is_bool_dtype(non_null):
        return "boolean"
    if pd.api.types.is_numeric_dtype(non_null):
        return "numeric"
    try:
        if pd.to_numeric(non_null, errors="coerce").notna().mean() >= 0.8:
            return "numeric"
    except Exception:
        pass
    parsed = pd.to_datetime(non_null.astype(str).head(20), errors="coerce", utc=True)
    if parsed.notna().mean() >= 0.8:
        return "timestamp"
    try:
        if non_null.nunique() / len(non_null) < 0.05:
            return "categorical"
    except TypeError:
        return "string"
    return "string"


def clean_val(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        v = v.item()
    return v


def row_to_dict(r):
    d = {}
    for c in COLS:
        val = clean_val(r[c])
        if c in ("Customer ID", "Quantity") and isinstance(val, float) and val == int(val):
            val = int(val)
        if c == "InvoiceDate" and val is not None:
            val = str(val)
        d[c] = val
    return d


def violated_rules_for(r):
    vr = []
    if r["_custid_null"]:
        vr.append("customer_id_not_null")
    if r["_desc_null"]:
        vr.append("description_not_null")
    if r["_price_nonpos"] and not r["_is_cancel"]:
        vr.append("price_positive")
    if r["_qty_neg"] and not r["_is_cancel"]:
        vr.append("quantity_min")
    if r["_nonprod"]:
        vr.append("stockcode_is_product")
    return sorted(set(vr))


def main():
    df = pd.read_csv(CSV_PATH)
    print(f"로드: {CSV_PATH}  shape={df.shape}")

    sc = df["StockCode"].astype(str).str.upper()
    df["_is_cancel"] = df["Invoice"].astype(str).str.upper().str.startswith("C")
    df["_custid_null"] = df["Customer ID"].isna()
    df["_desc_null"] = df["Description"].isna()
    df["_qty_neg"] = df["Quantity"] < 0
    df["_price_nonpos"] = df["Price"] <= 0
    df["_nonprod"] = sc.isin(NONPROD) | sc.str.startswith("GIFT")
    general, cid = [], 1

    # ① normal (완전 정상행) 18개
    clean_mask = (
        ~df["_custid_null"]
        & ~df["_desc_null"]
        & (df["Quantity"] > 0)
        & (df["Price"] > 0)
        & ~df["_is_cancel"]
        & ~df["_nonprod"]
    )
    for _, r in df[clean_mask].sample(18, random_state=SEED).iterrows():
        general.append(
            {
                "id": f"ec_normal_{cid:03d}",
                "input": {"row": row_to_dict(r)},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {"note": "정상 판매행", "difficulty": "easy"},
            }
        )
        cid += 1

    # ② 위반 케이스 (채점 가능한 규칙만)
    def add(mask, slug, note, diff, n):
        nonlocal cid
        sub = df[mask]
        if len(sub) == 0:
            print(f"  [WARN] {slug}: 해당 행 없음")
            return
        for _, r in sub.sample(min(n, len(sub)), random_state=SEED + cid).iterrows():
            vr = violated_rules_for(r) or [slug]
            general.append(
                {
                    "id": f"ec_{slug}_{cid:03d}",
                    "input": {"row": row_to_dict(r)},
                    "expected": {"has_violation": True, "violated_rules": vr},
                    "metadata": {"note": note, "difficulty": diff},
                }
            )
            cid += 1

    add(
        df["_custid_null"]
        & ~df["_desc_null"]
        & (df["Quantity"] > 0)
        & (df["Price"] > 0)
        & ~df["_is_cancel"]
        & ~df["_nonprod"],
        "customer_id_not_null",
        "Customer ID 결측",
        "easy",
        5,
    )
    add(df["_desc_null"], "description_not_null", "Description 결측", "easy", 4)
    add(
        df["_price_nonpos"] & ~df["_is_cancel"] & ~df["_desc_null"],
        "price_positive",
        "비취소 거래에 0 이하 가격",
        "medium",
        4,
    )
    add(
        df["_qty_neg"] & ~df["_is_cancel"] & ~df["_desc_null"],
        "quantity_min",
        "비취소 거래에 음수 수량",
        "medium",
        4,
    )
    add(
        df["_nonprod"] & ~df["_desc_null"],
        "stockcode_is_product",
        "비상품 코드(POST/DOT/M 등)",
        "hard",
        2,
    )

    with open(GENERAL_OUT, "w", encoding="utf-8") as f:
        for c in general:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # ③ 이상치 골든셋 (column × method)
    profile = {}
    for col in COLS:
        dt = detect_column_type(df[col])
        info = {"dtype": dt}
        if dt == "numeric":
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            info["std"] = round(float(s.std()), 3)
        profile[col] = info

    specs = [
        ("Quantity", "zscore", True, "수량 zscore 이상치 규칙 생성 필요(수치형)", "easy"),
        ("Quantity", "iqr", True, "수량 IQR 이상치 규칙 생성 필요(편향 수치형)", "easy"),
        ("Price", "zscore", True, "가격 zscore 이상치 규칙 생성 필요(수치형)", "easy"),
        ("Price", "iqr", True, "가격 IQR 이상치 규칙 생성 필요(편향 수치형)", "easy"),
        ("Country", "frequency", True, "Country 빈도 이상치 규칙 생성 필요(범주형)", "medium"),
        ("Description", "iqr", False, "string 컬럼에 IQR 생성 금지(오답 유도)", "medium"),
        ("Description", "zscore", False, "string 컬럼에 zscore 생성 금지(오답 유도)", "hard"),
        ("Country", "iqr", False, "범주형 컬럼에 IQR 생성 금지(오답 유도)", "hard"),
    ]
    anomaly = []
    for i, (col, method, exists, note, diff) in enumerate(specs, 1):
        anomaly.append(
            {
                "id": f"ec_anom_{i:03d}",
                "input": {"column": col, "method": method, "column_profile": profile[col]},
                "expected": {"has_anomaly_rule": exists},
                "metadata": {"note": note, "difficulty": diff},
            }
        )

    with open(ANOMALY_OUT, "w", encoding="utf-8") as f:
        for c in anomaly:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # ── 요약 ──
    print(f"\n일반 골든셋  : {GENERAL_OUT}  ({len(general)}개)")
    print("  난이도:", dict(Counter(c["metadata"]["difficulty"] for c in general)))
    print(
        "  위반:",
        sum(c["expected"]["has_violation"] for c in general),
        "/ 정상:",
        sum(not c["expected"]["has_violation"] for c in general),
    )
    print(
        f"이상치 골든셋: {ANOMALY_OUT}  ({len(anomaly)}개)  "
        f"true={sum(a['expected']['has_anomaly_rule'] for a in anomaly)} "
        f"false={sum(not a['expected']['has_anomaly_rule'] for a in anomaly)}"
    )
    print("  수치형 프로파일:", {k: v for k, v in profile.items() if v["dtype"] == "numeric"})
    print("  컬럼 dtype:", {k: v["dtype"] for k, v in profile.items()})


if __name__ == "__main__":
    main()
