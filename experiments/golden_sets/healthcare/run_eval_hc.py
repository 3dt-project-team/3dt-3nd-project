"""
Healthcare 골든셋 평가 실행기
=====================================
Clinical / Billing 두 서브도메인을 --sub 플래그로 선택.

[사용법]
    # Clinical (기본)
    python experiments/golden_sets/healthcare/run_eval_hc.py --model gpt-4.1-mini --sub clinical --csv "C:/경로/full_dataset.csv"

    # Billing
    python experiments/golden_sets/healthcare/run_eval_hc.py --model gpt-4.1-mini --sub billing --csv "C:/경로/healthcare_dataset.csv"

    # Kaggle 자동 다운로드 (kagglehub 설정 완료 시)
    python experiments/golden_sets/healthcare/run_eval_hc.py --model gpt-4.1-mini --sub clinical

    # 전체 모델 순회 (PowerShell)
    foreach ($m in @("gpt-4.1-mini","Mistral-Large-3","Llama-3.3-70B-Instruct","Llama-4-Maverick-17B-128E-Instruct-FP8")) {
        python experiments/golden_sets/healthcare/run_eval_hc.py --model $m --sub clinical --csv "C:/경로/full_dataset.csv"
        python experiments/golden_sets/healthcare/run_eval_hc.py --model $m --sub billing --csv "C:/경로/healthcare_dataset.csv"
    }
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

# ── 엔드포인트 ───────────────────────────────────────────
AZURE_BASE_URL = "https://team4-foundry-eastus.openai.azure.com/openai/v1"
OLLAMA_BASE_URL = "http://localhost:11434/v1"

# ── 서브도메인별 설정 ────────────────────────────────────
HC_DIR = Path(__file__).parent

SUB_CONFIG = {
    "clinical": {
        "kaggle_dataset": "mdsajjadullah/synthetic-medical-ehr-dataset-10k",
        "kaggle_table": "full_dataset.csv",
        "domain": "hc_clinical",
        "golden": HC_DIR / "golden_set_hc_clinical_v1.jsonl",
        "anomaly": HC_DIR / "golden_set_hc_clinical_anomaly_v1.jsonl",
    },
    "billing": {
        "kaggle_dataset": "prasad22/healthcare-dataset",
        "kaggle_table": "healthcare_dataset.csv",
        "domain": "hc_billing",
        "golden": HC_DIR / "golden_set_hc_billing_v1.jsonl",
        "anomaly": HC_DIR / "golden_set_hc_billing_anomaly_v1.jsonl",
    },
}

OUTPUT_DIR = HC_DIR / "outputs"


# ── 프로파일링 (run_eval_ec.py 동일) ─────────────────────


def detect_column_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "unknown"
    if pd.api.types.is_bool_dtype(non_null):
        return "boolean"
    if pd.api.types.is_numeric_dtype(non_null):
        return "numeric"
    try:
        converted = pd.to_numeric(non_null, errors="coerce")
        if converted.notna().mean() >= 0.8:
            return "numeric"
    except Exception:
        pass
    sample = non_null.astype(str).head(20)
    parsed = pd.to_datetime(sample, errors="coerce", utc=True)
    if parsed.notna().mean() >= 0.8:
        return "timestamp"
    try:
        unique_ratio = non_null.nunique() / len(non_null)
    except TypeError:
        return "string"
    if unique_ratio < 0.05:
        return "categorical"
    return "string"


def safe_sample_values(series: pd.Series, n=10) -> list:
    values = series.dropna().head(n).tolist()
    result = []
    for v in values:
        try:
            json.dumps(v)
            result.append(v)
        except TypeError:
            result.append(str(v))
    return result


def auto_profile(df: pd.DataFrame) -> dict:
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


# ── 프롬프트 빌더 (run_eval_ec.py 동일) ──────────────────


def build_stage1_prompt(profile: dict, domain_name: str) -> list[dict]:
    compact = json.dumps(profile, ensure_ascii=False, indent=2)
    system = """
You are a senior data quality engineer building a domain-agnostic automated data quality platform.

== NULL HANDLING STRATEGY ==
Options: drop, allow, fill_default, fill_mean, fill_median, fill_mode,
         fill_forward, fill_backward, fill_interpolate, fill_conditional

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
For free-text columns: identify checks needed (profanity, spam, hate_speech, pii).
If no free-text columns, return empty list [].

Return ONLY valid JSON. No markdown.
""".strip()
    user = f"""
Domain: {domain_name}

Column profile:
{compact}

Return:
{{
  "null_strategies": {{
    "<col>": {{
      "strategy": "...",
      "default_value": null,
      "reason": "..."
    }}
  }},
  "text_quality_columns": []
}}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_stage2_prompt(profile: dict, domain_name: str) -> list[dict]:
    key_profile = {
        col: info
        for col, info in profile.items()
        if info["null_rate"] < 0.1
        or info["dtype"] in ("categorical", "boolean", "timestamp")
        or info["dtype"] == "numeric"
    }
    compact = json.dumps(key_profile, ensure_ascii=False, indent=2)
    domain_abbr = domain_name[:4].upper()
    system = """
You are a senior data quality engineer.

== VALIDATION RULES ==
You MUST use ONLY these exact expectation_type values (no other names allowed):
- expect_column_values_to_not_be_null   : column must not be null
- expect_column_values_to_be_unique     : column values must be unique
- expect_column_values_to_match_regex   : column must match regex (kwargs: {"regex": "..."})
- expect_column_values_to_be_in_set     : column must be one of allowed values
                                          (kwargs: {"value_set": [...]})
- expect_column_values_to_be_between    : column value must be >= min (kwargs: {"min_value": N})
- expect_column_min_to_be_between       : column min must be > 0 (kwargs: {"min_value": 0})

Rules:
- Do NOT use any other expectation_type name
- Do NOT generate string length rules
- One rule per expectation_type per column, no duplicates
- For value_set rules: infer standardized/clean values from column name and context,
  NOT raw dirty samples
  (e.g. Transaction_Status -> ["Completed", "Failed", "Pending"],
   Payment_Method -> ["Credit Card", "PayPal", "Cash"])
- severity: critical / warning / info
- Categorical high unique_count (>10): WARNING not CRITICAL

== ANOMALY RULES ==
Generate anomaly_rules for ALL qualifying columns. Do NOT skip columns.
- zscore   : MUST generate for every numeric column with std > 0 (threshold: 3)
- iqr      : MUST generate for every skewed numeric column (threshold: 1.5)
- frequency: MUST generate for every categorical column (threshold: 3)
- Do NOT apply zscore/iqr to string or categorical columns
- Each rule must have: rule_id, name, columns (list), method, threshold, severity, reason

Return ONLY valid JSON. No markdown.
""".strip()
    user = f"""
Domain: {domain_name}
Profile:
{compact}

Return:
{{
  "suite_name": "{domain_name}_quality_suite",
  "domain": "{domain_name}",
  "generated_at": "{datetime.utcnow().isoformat()}Z",
  "expectations": [
    {{
      "rule_id": "RULE_{domain_abbr}_001",
      "expectation_type": "...",
      "column": "...",
      "kwargs": {{}},
      "severity": "critical|warning|info",
      "enabled": true,
      "reason": "..."
    }}
  ],
  "anomaly_rules": [
    {{
      "rule_id": "RULE_{domain_abbr}_010",
      "name": "...",
      "columns": ["..."],
      "method": "zscore|iqr|frequency",
      "threshold": null,
      "severity": "warning",
      "reason": "..."
    }}
  ]
}}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── AI 호출 (429 지수 백오프 재시도) ──────────────────────


def call_ai(
    client: OpenAI,
    model: str,
    messages: list[dict],
    label: str,
    max_retries: int = 5,
    base_wait: int = 30,
) -> dict:
    print(f"  [{label}] 호출 중...")
    response = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=8000,
            )
            break
        except RateLimitError:
            if attempt == max_retries - 1:
                print(f"  [ERROR] {max_retries}회 재시도 모두 실패")
                raise
            wait = base_wait * (2**attempt)
            print(f"  [Rate Limit] {attempt + 1}/{max_retries}회 - {wait}초 대기...")
            time.sleep(wait)

    raw = response.choices[0].message.content.strip()
    usage = response.usage
    total = usage.total_tokens if usage else "?"
    print(f"  [{label}] 완료 | 토큰: {total}")

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON 파싱 실패: {e}")
        print(f"  [RAW] {raw[:300]}")
        return {}


# ── 데이터 로드 ───────────────────────────────────────────


def load_table_csv(csv_path: str) -> tuple[pd.DataFrame, str]:
    """로컬 CSV 파일 직접 로드."""
    df = pd.read_csv(csv_path)
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() >= 0.5:
            df[col] = converted
    return df, os.path.basename(csv_path)


def load_table_kaggle(dataset_id: str, table: str | None) -> tuple[pd.DataFrame, str]:
    """Kaggle 데이터셋에서 CSV 로드."""
    try:
        import kagglehub

        path = kagglehub.dataset_download(dataset_id)
    except Exception:
        owner, name = dataset_id.split("/")
        cache_base = Path.home() / ".cache" / "kagglehub" / "datasets" / owner / name / "versions"
        versions = sorted(cache_base.iterdir()) if cache_base.exists() else []
        if not versions:
            raise
        path = str(versions[-1])

    csv_files = []
    for root, _, files in os.walk(path):
        for f in files:
            if f.endswith(".csv"):
                csv_files.append(os.path.join(root, f))

    if not csv_files:
        raise FileNotFoundError(f"CSV 파일 없음: {path}")

    if table:
        matched = [f for f in csv_files if os.path.basename(f) == table]
        if not matched:
            available = [os.path.basename(f) for f in csv_files]
            raise FileNotFoundError(f"테이블 '{table}' 없음. 사용 가능: {available}")
        target = matched[0]
    elif len(csv_files) == 1:
        target = csv_files[0]
    else:
        available = [os.path.basename(f) for f in csv_files]
        raise ValueError(f"CSV가 여러 개입니다. --table 로 지정하세요: {available}")

    df = pd.read_csv(target)
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() >= 0.5:
            df[col] = converted
    return df, os.path.basename(target)


# ── 메인 ──────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Healthcare 골든셋 평가 실행기 (Clinical / Billing)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--model",
        required=True,
        help="배포 이름. Azure: gpt-4.1-mini, Mistral-Large-3 등",
    )
    parser.add_argument(
        "--sub",
        required=True,
        choices=["clinical", "billing"],
        help="서브도메인: clinical (임상 EHR) / billing (보험 청구)",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="로컬 CSV 경로 (지정하면 Kaggle 다운로드 생략)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Ollama 로컬 추론 사용 (localhost:11434)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AZURE_API_KEY", ""),
        help="Azure API 키 (기본: 환경변수 AZURE_API_KEY)",
    )
    args = parser.parse_args()

    # ── 서브도메인 설정 로드 ──
    cfg = SUB_CONFIG[args.sub]
    domain = cfg["domain"]
    golden_path = str(cfg["golden"])
    anomaly_path = str(cfg["anomaly"])

    print(f"{'=' * 60}")
    print(f"  Healthcare 평가: {args.sub.upper()} | 모델: {args.model}")
    print(f"{'=' * 60}")

    # ── 엔드포인트/키 선택 ──
    if args.local:
        base_url, api_key = OLLAMA_BASE_URL, "ollama"
        print(f"[모드] Ollama 로컬 ({base_url})")
    else:
        base_url, api_key = AZURE_BASE_URL, args.api_key
        if not api_key:
            print(
                "[ERROR] API 키가 없습니다. 환경변수 AZURE_API_KEY 를 설정하거나 "
                "--api-key 인자로 전달하세요.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[모드] Azure ({base_url})")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 데이터 로드
    if args.csv:
        print(f"[1/4] 로컬 CSV 로드 중... ({args.csv})")
        df, table_name = load_table_csv(args.csv)
    else:
        print(f"[1/4] Kaggle 데이터 로드 중... ({cfg['kaggle_dataset']})")
        df, table_name = load_table_kaggle(cfg["kaggle_dataset"], cfg["kaggle_table"])
    print(f"  테이블: {table_name} | {len(df):,}행 x {len(df.columns)}컬럼")

    # 2. 프로파일링
    print("[2/4] 컬럼 프로파일링 중...")
    profile = auto_profile(df)
    slim_profile = {col: info for col, info in profile.items() if info["null_rate"] < 0.95}
    print(f"  {len(slim_profile)}개 컬럼 -> AI 전달")

    # 3. 규칙 생성
    print(f"[3/4] 규칙 생성 중 (모델: {args.model} | 도메인: {domain})...")
    client = OpenAI(api_key=api_key, base_url=base_url)

    stage1 = call_ai(
        client, args.model, build_stage1_prompt(slim_profile, domain), "Stage1 NULL전략"
    )
    stage2 = call_ai(
        client, args.model, build_stage2_prompt(slim_profile, domain), "Stage2 검증규칙"
    )

    rules = {
        "suite_name": stage2.get("suite_name", f"{domain}_quality_suite"),
        "domain": domain,
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": args.model,
        "dataset": cfg["kaggle_dataset"],
        "table": table_name,
        "null_strategies": stage1.get("null_strategies", {}),
        "expectations": stage2.get("expectations", []),
        "anomaly_rules": stage2.get("anomaly_rules", []),
        "text_quality_columns": stage1.get("text_quality_columns", []),
    }
    print(
        f"  검증 규칙 {len(rules['expectations'])}개 | 이상치 규칙 {len(rules['anomaly_rules'])}개"
    )

    model_slug = args.model.replace("/", "_").replace(".", "-")
    rules_path = OUTPUT_DIR / f"rules_{domain}_{model_slug}.json"
    rules_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  규칙 저장 완료: {rules_path}")

    # 4. 평가
    print("[4/4] 골든셋 평가 실행...")
    # evaluate_golden_set.py는 golden_sets/ 루트에 있음
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from evaluate_golden_set import evaluate

    anomaly_file = anomaly_path if Path(anomaly_path).exists() else None
    if not Path(golden_path).exists():
        print(f"  [WARN] 골든셋 파일 없음: {golden_path} -> 평가 생략")
        return

    evaluate(str(rules_path), golden_path, anomaly_file)


if __name__ == "__main__":
    main()
