"""
HF 모델 비교 평가 (2차 - 신규 모델 추가)
============================================
동일한 도메인 감지 프롬프트를 여러 모델에 N회씩 던져서
형식/내용/비용/속도/안정성을 숫자로 측정하고 CSV로 저장한다.

2차 변경점: 1차 합격 2개 유지 + 신규 3개 추가
"""

import csv
import json
import os
import statistics
import time

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# ── 설정 ─────────────────────────────────────
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    raise ValueError(".env에 HF_TOKEN이 없습니다")

client = InferenceClient(api_key=HF_TOKEN)

N_RUNS = 5  # 모델당 반복 호출 횟수 (통계용)
EXPECTED_DOMAIN_KEYWORDS = ["wiki", "wikidata"]  # 정답 판정용 키워드

# ── 모델별 단가 (USD per 1M tokens, 2026년 기준 대략값) ──
# 정확한 값은 각 프로바이더 페이지에서 확인 후 갱신
MODEL_PRICING = {
    "Qwen/Qwen2.5-7B-Instruct": {"in": 0.20, "out": 0.20},
    "meta-llama/Llama-3.1-8B-Instruct": {"in": 0.20, "out": 0.20},
    "Qwen/Qwen3-8B": {"in": 0.20, "out": 0.20},
    "microsoft/Phi-4-mini-instruct": {"in": 0.10, "out": 0.10},
    "mistralai/Mistral-Small-3.1-24B-Instruct-2503": {"in": 0.30, "out": 0.30},
}

# ── 프롬프트 (1차와 동일) ──────────────────────
SYSTEM_PROMPT = """You are a data domain expert.
Identify the data domain from column names, dtypes, and sample values.
Return a JSON with:
- domain_name: short snake_case name (e.g. wikipedia_recentchange, nyc_taxi_trips)
- domain_description: one sentence describing the data
- key_columns: list of 3-5 most important columns
- data_characteristics: list of 2-3 notable characteristics
Return ONLY valid JSON. No markdown."""

USER_PROMPT = """Column profile:
{
  "title": {"dtype": "string", "sample": ["Q117866876", "Q7159521"]},
  "user": {"dtype": "string", "sample": ["Gerd Fahre", "Bargioni"]},
  "wiki": {"dtype": "categorical", "sample": ["wikidatawiki", "enwiki"]},
  "_bytes_changed": {"dtype": "numeric", "sample": [75, 835, -99999]},
  "type": {"dtype": "categorical", "sample": ["edit", "new", "log"]}
}

Identify the domain."""


# ── 단일 호출 (1회) ───────────────────────────
def single_call(model_id):
    """한 번 호출하고 측정값 dict 반환"""
    result = {
        "json_ok": False,
        "domain_correct": False,
        "latency": None,
        "in_tokens": None,
        "out_tokens": None,
        "error": None,
        "domain_name": None,
    }
    try:
        start = time.time()
        resp = client.chat_completion(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ],
            temperature=0,
            max_tokens=300,
        )
        result["latency"] = time.time() - start

        if resp.usage:
            result["in_tokens"] = resp.usage.prompt_tokens
            result["out_tokens"] = resp.usage.completion_tokens

        raw = resp.choices[0].message.content.strip()

        try:
            parsed = json.loads(raw)
            result["json_ok"] = True
            domain = str(parsed.get("domain_name", "")).lower()
            result["domain_name"] = domain
            result["domain_correct"] = any(kw in domain for kw in EXPECTED_DOMAIN_KEYWORDS)
        except json.JSONDecodeError:
            result["json_ok"] = False

    except Exception as e:
        result["error"] = str(e)

    return result


# ── 모델 평가 (N회 반복 + 집계) ─────────────────
def evaluate_model(model_id):
    print(f"\n{'=' * 60}")
    print(f"평가 중: {model_id}  (N={N_RUNS}회)")
    print(f"{'=' * 60}")

    runs = []
    for i in range(N_RUNS):
        r = single_call(model_id)
        runs.append(r)
        status = "✅" if r["json_ok"] else ("❌" if r["error"] is None else "💥")
        latency_str = f"{r['latency']:.2f}s" if r["latency"] else "N/A"
        print(
            f"  [{i + 1}/{N_RUNS}] {status} latency={latency_str}"
            + (f"  ERROR: {r['error'][:60]}" if r["error"] else "")
        )

    errors = [r for r in runs if r["error"] is not None]
    valid = [r for r in runs if r["error"] is None]

    error_rate = len(errors) / N_RUNS * 100
    json_success_rate = sum(r["json_ok"] for r in valid) / N_RUNS * 100 if valid else 0
    domain_correct_rate = sum(r["domain_correct"] for r in valid) / N_RUNS * 100 if valid else 0

    latencies = [r["latency"] for r in valid if r["latency"] is not None]
    avg_latency = statistics.mean(latencies) if latencies else None
    p95_latency = (
        sorted(latencies)[int(len(latencies) * 0.95) - 1]
        if len(latencies) >= 2
        else (latencies[0] if latencies else None)
    )
    std_latency = statistics.pstdev(latencies) if len(latencies) >= 2 else 0

    avg_in = (
        statistics.mean([r["in_tokens"] for r in valid if r["in_tokens"]])
        if any(r["in_tokens"] for r in valid)
        else None
    )
    avg_out = (
        statistics.mean([r["out_tokens"] for r in valid if r["out_tokens"]])
        if any(r["out_tokens"] for r in valid)
        else None
    )

    cost_per_call = None
    if avg_in and avg_out and model_id in MODEL_PRICING:
        p = MODEL_PRICING[model_id]
        cost_per_call = (avg_in * p["in"] + avg_out * p["out"]) / 1_000_000

    return {
        "model": model_id,
        "json_success_rate": round(json_success_rate, 1),
        "domain_correct_rate": round(domain_correct_rate, 1),
        "cost_per_call": round(cost_per_call, 8) if cost_per_call else "N/A",
        "avg_latency": round(avg_latency, 2) if avg_latency else "N/A",
        "p95_latency": round(p95_latency, 2) if p95_latency else "N/A",
        "std_latency": round(std_latency, 2),
        "error_rate": round(error_rate, 1),
        "sample_domain": next((r["domain_name"] for r in valid if r["domain_name"]), "N/A"),
    }


# ── 메인 ─────────────────────────────────────
# 1차 합격 2개 유지 + 신규 3개 추가
models_to_test = [
    "Qwen/Qwen2.5-7B-Instruct",  # 1차 합격 (베이스라인)
    "meta-llama/Llama-3.1-8B-Instruct",  # 1차 합격 (안정성)
    "Qwen/Qwen3-8B",  # 신규: Qwen 신세대
    "microsoft/Phi-4-mini-instruct",  # 신규: 초경량 저비용
    "mistralai/Mistral-Small-3.1-24B-Instruct-2503",  # 신규: 고품질 + tool use
]

if __name__ == "__main__":
    all_results = []
    for model_id in models_to_test:
        all_results.append(evaluate_model(model_id))

    print(f"\n\n{'=' * 100}")
    print("최종 결과 비교표")
    print(f"{'=' * 100}")
    headers = [
        "model",
        "json_success_rate",
        "domain_correct_rate",
        "cost_per_call",
        "avg_latency",
        "p95_latency",
        "std_latency",
        "error_rate",
        "sample_domain",
    ]
    print(" | ".join(h[:18] for h in headers))
    print("-" * 100)
    for r in all_results:
        print(" | ".join(str(r[h])[:18] for h in headers))

    csv_path = os.path.join(os.path.dirname(__file__), "model_comparison_results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\n✅ CSV 저장 완료: {csv_path}")
    print("→ 이 파일 결과 그대로 복사해서 보여주세요!")
