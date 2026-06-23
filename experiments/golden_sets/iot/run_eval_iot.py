"""
제조·IoT 골든셋 평가 실행기
Sensor / Mfg 두 서브도메인을 --sub 플래그로 선택.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from openai import OpenAI, RateLimitError

AZURE_BASE_URL = "https://team4-foundry-eastus.openai.azure.com/openai/v1"
OLLAMA_BASE_URL = "http://localhost:11434/v1"

IOT_DIR = Path(__file__).parent
SUB_CONFIG = {
    "sensor": {
        "kaggle_dataset": "stephanmatzka/predictive-maintenance-dataset-ai4i-2020",
        "kaggle_table": "ai4i2020.csv",
        "domain": "iot_sensor",
        "golden": IOT_DIR / "golden_set_iot_sensor_v1.jsonl",
        "anomaly": IOT_DIR / "golden_set_iot_sensor_anomaly_v1.jsonl",
    },
    "mfg": {
        "kaggle_dataset": "rabieelkharoua/predicting-manufacturing-defects-dataset",
        "kaggle_table": "manufacturing_defect_dataset.csv",
        "domain": "iot_mfg",
        "golden": IOT_DIR / "golden_set_iot_mfg_v1.jsonl",
        "anomaly": IOT_DIR / "golden_set_iot_mfg_anomaly_v1.jsonl",
    },
}
OUTPUT_DIR = IOT_DIR / "outputs"


def detect_column_type(series):
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
    except:
        pass
    sample = non_null.astype(str).head(20)
    if pd.to_datetime(sample, errors="coerce", utc=True).notna().mean() >= 0.8:
        return "timestamp"
    try:
        if non_null.nunique() / len(non_null) < 0.05:
            return "categorical"
    except TypeError:
        return "string"
    return "string"


def safe_sample_values(series, n=10):
    result = []
    for v in series.dropna().head(n).tolist():
        try:
            json.dumps(v)
            result.append(v)
        except TypeError:
            result.append(str(v))
    return result


def auto_profile(df):
    profile = {}
    for col in df.columns:
        series = df[col]
        dtype = detect_column_type(series)
        if dtype == "numeric" and pd.api.types.is_object_dtype(series):
            series = pd.to_numeric(series, errors="coerce")
        non_null = series.dropna()
        col_info = {
            "dtype": dtype,
            "null_rate": round(series.isna().mean(), 3),
            "unique_count": int(non_null.nunique()) if not non_null.empty else 0,
            "sample": safe_sample_values(series),
        }
        if dtype == "numeric" and not non_null.empty:
            col_info["mean"] = round(float(non_null.mean()), 3)
            col_info["std"] = round(float(non_null.std()), 3)
        profile[col] = col_info
    return profile


def build_stage1_prompt(profile, domain_name):
    compact = json.dumps(profile, ensure_ascii=False, indent=2)
    system = """You are a senior data quality engineer building a domain-agnostic automated data quality platform.
== NULL HANDLING STRATEGY ==
Options: drop, allow, fill_default, fill_mean, fill_median, fill_mode, fill_forward, fill_backward, fill_interpolate, fill_conditional
Rules:
- Identifier columns (id, uuid, key, request_id in name): ALWAYS "drop"
- Boolean columns: "fill_mode"
- null_rate > 0.8: "allow"
- Free-text (comment, title, description): "fill_default" with ""
- Timestamp: "fill_forward" or "drop", NEVER "fill_mean"
- Categorical null_rate > 0.1: "fill_mode"
- Skewed numeric (high std vs mean): "fill_median"
- Normal numeric: "fill_mean"
== TEXT QUALITY RULES ==
For free-text columns: identify checks needed. If no free-text columns, return empty list [].
Return ONLY valid JSON. No markdown.""".strip()
    user = f'Domain: {domain_name}\nColumn profile:\n{compact}\nReturn:\n{{\n  "null_strategies": {{\n    "<col>": {{"strategy": "...", "default_value": null, "reason": "..."}}\n  }},\n  "text_quality_columns": []\n}}'
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_stage2_prompt(profile, domain_name):
    key_profile = {
        c: i
        for c, i in profile.items()
        if i["null_rate"] < 0.1
        or i["dtype"] in ("categorical", "boolean", "timestamp")
        or i["dtype"] == "numeric"
    }
    compact = json.dumps(key_profile, ensure_ascii=False, indent=2)
    da = domain_name[:4].upper()
    system = """You are a senior data quality engineer.
== VALIDATION RULES ==
You MUST use ONLY these exact expectation_type values:
- expect_column_values_to_not_be_null, expect_column_values_to_be_unique, expect_column_values_to_match_regex, expect_column_values_to_be_in_set, expect_column_values_to_be_between, expect_column_min_to_be_between
Rules: Do NOT use any other expectation_type. One rule per type per column. For value_set: infer clean values from context. severity: critical/warning/info.
== ANOMALY RULES ==
- zscore: every numeric with std>0 (threshold:3)
- iqr: every skewed numeric (threshold:1.5)
- frequency: every categorical (threshold:3)
- Do NOT apply zscore/iqr to string/categorical
Return ONLY valid JSON. No markdown.""".strip()
    user = f'Domain: {domain_name}\nProfile:\n{compact}\nReturn:\n{{"suite_name":"{domain_name}_quality_suite","domain":"{domain_name}","generated_at":"{datetime.utcnow().isoformat()}Z","expectations":[{{"rule_id":"RULE_{da}_001","expectation_type":"...","column":"...","kwargs":{{}},"severity":"critical","enabled":true,"reason":"..."}}],"anomaly_rules":[{{"rule_id":"RULE_{da}_010","name":"...","columns":["..."],"method":"zscore|iqr|frequency","threshold":null,"severity":"warning","reason":"..."}}]}}'
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_ai(client, model, messages, label, max_retries=5, base_wait=30):
    print(f"  [{label}] 호출 중...")
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model, messages=messages, temperature=0, max_tokens=8000
            )
            break
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = base_wait * (2**attempt)
            print(f"  [Rate Limit] {attempt + 1}/{max_retries} - {wait}s 대기...")
            time.sleep(wait)
    raw = response.choices[0].message.content.strip()
    print(f"  [{label}] 완료 | 토큰: {response.usage.total_tokens if response.usage else '?'}")
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON 파싱 실패: {e}\n  [RAW] {raw[:300]}")
        return {}


def load_table_csv(csv_path):
    df = pd.read_csv(csv_path)
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() >= 0.5:
            df[col] = converted
    return df, os.path.basename(csv_path)


def main():
    parser = argparse.ArgumentParser(description="IoT/Manufacturing 골든셋 평가 실행기")
    parser.add_argument("--model", required=True)
    parser.add_argument("--sub", required=True, choices=["sensor", "mfg"])
    parser.add_argument("--csv", default=None, help="로컬 CSV 경로")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--api-key", default=os.environ.get("AZURE_API_KEY", ""))
    args = parser.parse_args()

    cfg = SUB_CONFIG[args.sub]
    domain = cfg["domain"]
    golden_path, anomaly_path = str(cfg["golden"]), str(cfg["anomaly"])

    print(f"{'=' * 60}\n  IoT 평가: {args.sub.upper()} | 모델: {args.model}\n{'=' * 60}")

    if args.local:
        base_url, api_key = OLLAMA_BASE_URL, "ollama"
    else:
        base_url, api_key = AZURE_BASE_URL, args.api_key
        if not api_key:
            print("[ERROR] AZURE_API_KEY 없음", file=sys.stderr)
            sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.csv:
        print(f"[1/4] 로컬 CSV 로드... ({args.csv})")
        df, table_name = load_table_csv(args.csv)
    else:
        print("[ERROR] --csv 필요", file=sys.stderr)
        sys.exit(1)
    print(f"  {table_name} | {len(df):,}행 x {len(df.columns)}컬럼")

    print("[2/4] 프로파일링...")
    profile = auto_profile(df)
    slim = {c: i for c, i in profile.items() if i["null_rate"] < 0.95}
    print(f"  {len(slim)}컬럼 → AI")

    print(f"[3/4] 규칙 생성 (모델: {args.model})...")
    client = OpenAI(api_key=api_key, base_url=base_url)
    s1 = call_ai(client, args.model, build_stage1_prompt(slim, domain), "Stage1")
    s2 = call_ai(client, args.model, build_stage2_prompt(slim, domain), "Stage2")

    rules = {
        "suite_name": s2.get("suite_name", f"{domain}_suite"),
        "domain": domain,
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": args.model,
        "dataset": cfg["kaggle_dataset"],
        "table": table_name,
        "null_strategies": s1.get("null_strategies", {}),
        "expectations": s2.get("expectations", []),
        "anomaly_rules": s2.get("anomaly_rules", []),
        "text_quality_columns": s1.get("text_quality_columns", []),
    }
    print(f"  검증 {len(rules['expectations'])}개 | 이상치 {len(rules['anomaly_rules'])}개")

    slug = args.model.replace("/", "_").replace(".", "-")
    rp = OUTPUT_DIR / f"rules_{domain}_{slug}.json"
    rp.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  저장: {rp}")

    print("[4/4] 골든셋 평가...")
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from evaluate_golden_set import evaluate

    af = anomaly_path if Path(anomaly_path).exists() else None
    if not Path(golden_path).exists():
        print(f"  [WARN] 골든셋 없음: {golden_path}")
        return
    evaluate(str(rp), golden_path, af)


if __name__ == "__main__":
    main()
