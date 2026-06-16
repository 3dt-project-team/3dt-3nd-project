"""
골든셋 기반 모델 비교 평가 스크립트 (Phase 3)
============================================
golden_set_ecommerce_v1.jsonl을 읽어서
여러 모델에 각각 평가시키고 TPR/TNR/정확도를 비교한다.

rate limit 대응: 호출 텀 1.5초 + 429 에러 시 재시도
"""

import csv
import json
import os
import time

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    raise ValueError(".env에 HF_TOKEN이 없습니다")

client = InferenceClient(api_key=HF_TOKEN)

# 비교할 모델 — 한 번에 하나씩 돌리는 걸 권장 (rate limit 때문)
# 먼저 Qwen만 돌리고, 끝나면 주석 바꿔서 Llama 돌리기
MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    # "meta-llama/Llama-3.1-8B-Instruct",
]

GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "golden_set_ecommerce_v1.jsonl")

RULES_TEXT = """검증 규칙:
- R1: order_id는 null이면 안 됨
- R2: user_email은 null이면 안 됨
- R3: product_name은 null이면 안 됨
- R4: price는 0 이상이어야 함 (단, 증정품은 0원 가능)
- R5: quantity는 1 이상의 정수여야 함
- R6: discount_rate는 0~100 범위 (단, 100% 전액할인 프로모션 가능)
- R7: user_email은 올바른 이메일 형식이어야 함
- R8: status는 [pending, paid, shipped, delivered, cancelled] 중 하나
- R9: order_date는 미래 날짜가 아니어야 함 (오늘: 2026-06-15)"""

SYSTEM_PROMPT = f"""You are a data quality validator for ecommerce order data.
{RULES_TEXT}

Given a data row, determine if it violates any rule.
Consider domain context: free gifts can have price=0, full discount (100%) can be a valid promotion.

Return ONLY valid JSON, no markdown:
{{
  "has_violation": true or false,
  "violated_rules": ["R4", ...]
}}"""


def evaluate_case(model_id, row, max_retries=3):
    """모델에게 row를 주고 위반 여부 판단. rate limit 시 재시도."""
    user_prompt = f"Data row:\n{json.dumps(row, ensure_ascii=False)}\n\nValidate this row."
    for attempt in range(max_retries):
        try:
            resp = client.chat_completion(
                model=model_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=150,
            )
            raw = resp.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(raw)
            return {
                "has_violation": bool(parsed.get("has_violation", False)),
                "error": None,
            }
        except Exception as e:
            err = str(e)
            # rate limit이면 길게 대기 후 재시도
            if "429" in err or "rate" in err.lower() or "limit" in err.lower():
                wait = 10 * (attempt + 1)  # 10초, 20초, 30초
                print(f"      ⏳ rate limit, {wait}초 대기 후 재시도...")
                time.sleep(wait)
                continue
            else:
                return {"has_violation": None, "error": err}
    return {"has_violation": None, "error": "max retries exceeded"}


def evaluate_model(model_id, cases):
    print(f"\n{'=' * 60}")
    print(f"평가 중: {model_id}")
    print(f"{'=' * 60}")

    tp = tn = fp = fn = errors = 0
    wrong_cases = []

    for i, case in enumerate(cases):
        row = case["input"]["row"]
        truth = case["expected"]["has_violation"]
        result = evaluate_case(model_id, row)
        pred = result["has_violation"]

        if result["error"]:
            errors += 1
            status = "💥"
        elif truth and pred:
            tp += 1
            status = "✅TP"
        elif not truth and not pred:
            tn += 1
            status = "✅TN"
        elif not truth and pred:
            fp += 1
            status = "❌FP"
            wrong_cases.append((case["id"], "FP", case["metadata"]["note"]))
        elif truth and not pred:
            fn += 1
            status = "❌FN"
            wrong_cases.append((case["id"], "FN", case["metadata"]["note"]))

        err_msg = f"  ERR: {result['error'][:70]}" if result.get("error") else ""
        print(f"  [{i + 1:2d}/{len(cases)}] {status} {case['id']}{err_msg}")
        time.sleep(1.5)  # rate limit 여유

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0
    tpr = tp / (tp + fn) if (tp + fn) else 0
    tnr = tn / (tn + fp) if (tn + fp) else 0
    precision = tp / (tp + fp) if (tp + fp) else 0

    return {
        "model": model_id,
        "accuracy": round(accuracy * 100, 1),
        "tpr": round(tpr * 100, 1),
        "tnr": round(tnr * 100, 1),
        "precision": round(precision * 100, 1),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "errors": errors,
        "scored": total,  # 실제 채점된 개수 (에러 제외)
        "wrong_cases": wrong_cases,
    }


def run():
    cases = []
    with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
        for line in f:
            cases.append(json.loads(line))
    print(f"골든셋 {len(cases)}개 로드")

    all_results = []
    for model_id in MODELS:
        all_results.append(evaluate_model(model_id, cases))

    # 비교표 출력
    print(f"\n\n{'=' * 90}")
    print("모델 비교 결과")
    print(f"{'=' * 90}")
    print(
        f"{'모델':40s} {'채점됨':>6s} {'정확도':>7s} {'TPR':>7s} {'TNR':>7s} {'정밀도':>7s} {'에러':>5s}"
    )
    print("-" * 90)
    for r in all_results:
        print(
            f"{r['model']:40s} {r['scored']:>4}/{len(cases)} "
            f"{r['accuracy']:>6}% {r['tpr']:>6}% {r['tnr']:>6}% "
            f"{r['precision']:>6}% {r['errors']:>4}"
        )

    # 신뢰도 경고
    for r in all_results:
        if r["errors"] > 0:
            print(
                f"\n⚠️ {r['model']}: 에러 {r['errors']}건 발생 → 점수는 "
                f"채점된 {r['scored']}개 기준 (전체 {len(cases)}개 아님)"
            )

    # 각 모델 틀린 케이스
    for r in all_results:
        if r["wrong_cases"]:
            print(f"\n[{r['model']}] 틀린 케이스:")
            for cid, kind, note in r["wrong_cases"]:
                print(f"  {kind}  {cid}  ({note})")

    # CSV 저장
    csv_path = os.path.join(os.path.dirname(__file__), "eval_results_ecommerce.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "model",
                "scored",
                "total",
                "accuracy",
                "tpr",
                "tnr",
                "precision",
                "tp",
                "tn",
                "fp",
                "fn",
                "errors",
            ]
        )
        for r in all_results:
            writer.writerow(
                [
                    r["model"],
                    r["scored"],
                    len(cases),
                    r["accuracy"],
                    r["tpr"],
                    r["tnr"],
                    r["precision"],
                    r["tp"],
                    r["tn"],
                    r["fp"],
                    r["fn"],
                    r["errors"],
                ]
            )
    print(f"\n✅ CSV 저장: {csv_path}")


if __name__ == "__main__":
    run()
