"""
골든셋 평가 실행기

Kaggle 금융 데이터를 프로파일링하고 Azure AI Foundry 모델로 규칙을 생성한 뒤
evaluate_golden_set.py로 Precision/Recall/F1을 측정한다.

사용법:
    uv run python experiments/golden_sets/run_eval.py --model gpt-4.1-mini-gx-rulegen
    uv run python experiments/golden_sets/run_eval.py --model Llama-4-Maverick-17B-128E-Instruct-FP8
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import kagglehub
import pandas as pd
from openai import OpenAI

# ── 설정 (여기만 수정) ────────────────────────────────────
AZURE_BASE_URL = "https://datacops-openai.services.ai.azure.com/openai/v1"
AZURE_API_KEY = os.environ.get("AZURE_AI_API_KEY", "")

GOLDEN_PATH = Path(__file__).parent / "finance" / "golden_set_finance_v1.jsonl"
ANOMALY_PATH = Path(__file__).parent / "finance" / "golden_set_finance_anomaly_v1.jsonl"
OUTPUT_DIR = Path(__file__).parent / "finance" / "outputs"
# ─────────────────────────────────────────────────────────


# ── 프로파일링 (01_rules_generator에서 이식) ──────────────


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


# ── 프롬프트 빌더 (01_rules_generator에서 이식) ───────────


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
    # numeric은 null_rate 무관하게 항상 포함 (이상치 탐지 대상)
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
  (e.g. Transaction_Status → ["Completed", "Failed", "Pending"],
   Payment_Method → ["Credit Card", "PayPal", "Cash"])
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


# ── AI 호출 ───────────────────────────────────────────────


def call_ai(client: OpenAI, model: str, messages: list[dict], label: str) -> dict:
    import time

    print(f"  [{label}] 호출 중...")
    for attempt in range(8):
        try:
            # Responses API 먼저 시도 (Phi-4 계열은 chat.completions 쿼터 없음)
            try:
                response = client.responses.create(
                    model=model,
                    input=messages,
                    max_output_tokens=8000,
                )
                raw = response.output_text.strip()
                print(f"  [{label}] 완료 (responses API)")
            except Exception:
                # fallback: chat completions
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                    max_tokens=8000,
                )
                raw = response.choices[0].message.content.strip()
                usage = response.usage
                print(f"  [{label}] 완료 | 토큰: {usage.total_tokens}")
            break
        except Exception as e:
            if "429" in str(e) or "RateLimit" in str(e):
                wait = min(60 * (2**attempt), 300)
                print(f"  [{label}] Rate limit - {wait}sec wait, retry ({attempt + 1}/8)")
                time.sleep(wait)
            else:
                raise
    else:
        raise RuntimeError(f"[{label}] 8회 재시도 후 실패")

    # 마크다운 코드블록 제거
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON 파싱 실패: {e}")
        print(f"  [RAW] {raw[:300]}")
        return {}


# ── 데이터 로드 헬퍼 ──────────────────────────────────────


def load_table(dataset_id: str, table: str | None) -> tuple[pd.DataFrame, str]:
    """Kaggle 데이터셋에서 CSV 로드. table 미지정 시 단일 CSV 자동 선택."""
    try:
        path = kagglehub.dataset_download(dataset_id)
    except Exception:
        # 오프라인/403 시 로컬 캐시 경로 직접 사용
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

    # 모든 object 컬럼에 대해 숫자 변환 시도 (dirty 데이터 대응)
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() >= 0.5:
            df[col] = converted

    table_name = os.path.basename(target)
    return df, table_name


# ── 메인 ──────────────────────────────────────────────────


def main():
    golden_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(
        description="골든셋 평가 실행기",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
예시:
  # 기존 금융 트랜잭션 (단일 CSV)
  uv run python run_eval.py --model gpt-4.1-mini-gx-rulegen

  # TestDataBox transactions 테이블
  uv run python run_eval.py \\
    --model Llama-4-Maverick-17B-128E-Instruct-FP8 \\
    --dataset testdatabox/finance-fraud-and-loans-dataset-testdatabox \\
    --table transactions.csv \\
    --domain fin_transactions \\
    --golden golden_set_fin_transactions_v1.jsonl \\
    --anomaly golden_set_fin_transactions_anomaly_v1.jsonl

  # TestDataBox loans 테이블
  uv run python run_eval.py \\
    --model Llama-4-Maverick-17B-128E-Instruct-FP8 \\
    --dataset testdatabox/finance-fraud-and-loans-dataset-testdatabox \\
    --table loans.csv \\
    --domain fin_loans \\
    --golden golden_set_fin_loans_v1.jsonl \\
    --anomaly golden_set_fin_loans_anomaly_v1.jsonl
""",
    )
    parser.add_argument("--model", required=True, help="Azure AI Foundry 배포 이름")
    parser.add_argument(
        "--base-url",
        default=AZURE_BASE_URL,
        help="Azure AI Foundry 엔드포인트 (기본: datacops)",
    )
    parser.add_argument(
        "--dataset",
        default="alfarisbachmid/dirty-financial-transactions-dataset",
        help="Kaggle 데이터셋 ID (기본: dirty financial transactions)",
    )
    parser.add_argument(
        "--table",
        default=None,
        help="로드할 CSV 파일명. 데이터셋에 CSV가 여러 개면 필수.",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="도메인명 (기본: 테이블명에서 자동 추론)",
    )
    parser.add_argument(
        "--golden",
        default=str(golden_dir / "golden_set_finance_v1.jsonl"),
        help="일반 규칙 골든셋 JSONL 경로",
    )
    parser.add_argument(
        "--anomaly",
        default=str(golden_dir / "golden_set_finance_anomaly_v1.jsonl"),
        help="이상치 규칙 골든셋 JSONL 경로",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AZURE_AI_API_KEY", ""),
        help="Azure AI Foundry API 키 (기본: AZURE_AI_API_KEY 환경변수)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="프로파일링에 사용할 최대 행 수 (기본: 전체). 예: --max-rows 2000",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 데이터 로드 ───────────────────────────────────
    print(f"[1/4] Kaggle 데이터 로드 중... ({args.dataset})")
    df, table_name = load_table(args.dataset, args.table)
    if args.max_rows and len(df) > args.max_rows:
        df = df.sample(n=args.max_rows, random_state=42).reset_index(drop=True)
        print(f"  테이블: {table_name} | {args.max_rows:,}행 샘플 x {len(df.columns)}컬럼")
    else:
        print(f"  테이블: {table_name} | {len(df):,}행 x {len(df.columns)}컬럼")

    # ── 2. 프로파일링 ────────────────────────────────────
    print("[2/4] 컬럼 프로파일링 중...")
    profile = auto_profile(df)
    slim_profile = {col: info for col, info in profile.items() if info["null_rate"] < 0.95}
    print(f"  {len(slim_profile)}개 컬럼 → AI 전달")

    # ── 3. 규칙 생성 ─────────────────────────────────────
    domain = args.domain or table_name.replace(".csv", "").replace("-", "_")
    print(f"[3/4] 규칙 생성 중 (모델: {args.model} | 도메인: {domain})...")
    client = OpenAI(api_key=args.api_key, base_url=args.base_url, timeout=43200.0)

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
        "dataset": args.dataset,
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

    # ── 4. 골든셋 평가 ───────────────────────────────────
    print("[4/4] 골든셋 평가 실행...")
    sys.path.insert(0, str(Path(__file__).parent / "finance"))
    from evaluate_golden_set import evaluate

    golden_path = args.golden
    anomaly_path = args.anomaly if Path(args.anomaly).exists() else None

    if not Path(golden_path).exists():
        print(f"  [WARN] 골든셋 파일 없음: {golden_path} → 평가 생략")
        return

    evaluate(str(rules_path), golden_path, anomaly_path)


if __name__ == "__main__":
    main()
