"""
골든셋 평가 하니스 (Phase 3)
AI가 생성한 규칙을 골든셋과 비교해 Precision / Recall / F1 / FPR 계산

사용법:
    uv run python experiments/golden_sets/evaluate_golden_set.py \\
        --rules path/to/ai_generated_rules.json \\
        --golden experiments/golden_sets/golden_set_finance_v1.jsonl \\
        [--anomaly experiments/golden_sets/golden_set_finance_anomaly_v1.jsonl]

AI 규칙 JSON 형식 (01_rules_generator 출력):
    {
      "domain": "financial_transactions",
      "expectations": [
        {"column": "Price", "expectation_type": "expect_column_min_to_be_between",
         "kwargs": {"min_value": 0}, "severity": "critical", ...}
      ],
      "anomaly_rules": [
        {"name": "price_zscore", "columns": ["Price"], "method": "zscore", "threshold": 3}
      ]
    }
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ── 규칙 위반 판정 함수 ─────────────────────────────────────


def check_row_against_rules(row: dict, rules: dict) -> list[str]:
    """AI 생성 규칙 기준으로 row의 위반 규칙 ID 목록 반환."""
    violated = []

    for exp in rules.get("expectations", []):
        if not exp.get("enabled", True):
            continue

        col = exp.get("column")
        exp_type = exp.get("expectation_type", "")
        kwargs = exp.get("kwargs", {})
        rule_id = exp.get("rule_id", "")

        if col not in row:
            continue

        val = row[col]

        if exp_type == "expect_column_values_to_not_be_null":
            if val is None:
                violated.append(rule_id)

        elif exp_type == "expect_column_values_to_be_unique":
            # 단일 row 평가에서는 중복 판단 불가 → 스킵
            pass

        elif exp_type == "expect_column_values_to_match_regex":
            pattern = kwargs.get("regex", "")
            if val is not None and not re.match(pattern, str(val)):
                violated.append(rule_id)

        elif exp_type == "expect_column_min_to_be_between":
            min_val = kwargs.get("min_value")
            if val is not None and min_val is not None and float(val) <= float(min_val):
                violated.append(rule_id)

        elif exp_type == "expect_column_values_to_be_between":
            min_val = kwargs.get("min_value")
            if val is not None and min_val is not None and float(val) < float(min_val):
                violated.append(rule_id)

        elif exp_type == "expect_column_values_to_be_in_set":
            allowed = [str(v).lower() for v in kwargs.get("value_set", [])]
            if val is not None and str(val).lower() not in allowed:
                violated.append(rule_id)

    return violated


def check_anomaly_rules(rules: dict, golden_case: dict) -> bool:
    """이상치 규칙 골든셋 케이스에 대해 AI 규칙 존재 여부 확인."""
    col = golden_case["input"]["column"]
    method = golden_case["input"]["method"]
    dtype = golden_case["input"]["column_profile"]["dtype"]
    expected_exists = golden_case["expected"]["has_anomaly_rule"]

    # dtype 기반 적용 불가 판정 (AI가 이걸 알아서 걸러야 함)
    if dtype in ("string", "categorical") and method == "iqr":
        # AI가 규칙을 생성하지 않았어야 함
        ai_has_rule = any(
            r.get("columns", [r.get("column", "")]) == [col] and r.get("method") == method
            for r in rules.get("anomaly_rules", [])
        )
        return ai_has_rule == expected_exists

    if method == "zscore":
        std = golden_case["input"]["column_profile"].get("std", 1)
        if std == 0:
            ai_has_rule = any(
                col in r.get("columns", [r.get("column", "")]) and r.get("method") == "zscore"
                for r in rules.get("anomaly_rules", [])
            )
            return ai_has_rule == expected_exists

    # 일반 케이스: 규칙이 존재하는지 확인
    ai_has_rule = any(
        col in r.get("columns", [r.get("column", "")]) and r.get("method") == method
        for r in rules.get("anomaly_rules", [])
    )
    return ai_has_rule == expected_exists


# ── 메트릭 계산 ────────────────────────────────────────────


def compute_metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fpr": round(fpr, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


# ── 메인 평가 루프 ─────────────────────────────────────────


def evaluate(rules_path: str, golden_path: str, anomaly_path: str | None = None):
    with open(rules_path, encoding="utf-8") as f:
        rules = json.load(f)

    # 규칙 ID 매핑 빌드 (expectation_type → rule_id 추론)
    # AI 규칙에 rule_id가 없는 경우 expectation_type으로 매칭
    exp_type_to_rule_id: dict[str, str] = {}
    for exp in rules.get("expectations", []):
        if "rule_id" in exp:
            exp_type_to_rule_id[exp["expectation_type"]] = exp["rule_id"]

    # ── 일반 규칙 골든셋 평가 ──────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"골든셋: {golden_path}")
    print(f"{'=' * 60}")

    tp = fp = fn = tn = 0
    failures = []

    with open(golden_path, encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    for case in cases:
        row = case["input"]["row"]
        expected_violation = case["expected"]["has_violation"]
        expected_rules = set(case["expected"].get("violated_rules", []))

        violated = check_row_against_rules(row, rules)
        predicted_violation = len(violated) > 0

        if expected_violation and predicted_violation:
            tp += 1
        elif not expected_violation and not predicted_violation:
            tn += 1
        elif not expected_violation and predicted_violation:
            fp += 1
            failures.append(
                {
                    "id": case["id"],
                    "type": "FP",
                    "note": case["metadata"]["note"],
                    "predicted_rules": violated,
                }
            )
        else:
            fn += 1
            failures.append(
                {
                    "id": case["id"],
                    "type": "FN",
                    "note": case["metadata"]["note"],
                    "expected_rules": list(expected_rules),
                }
            )

    metrics = compute_metrics(tp, fp, fn, tn)
    print(f"총 케이스: {len(cases)}")
    print(f"  TP={tp}, FP={fp}, FN={fn}, TN={tn}")
    print(f"  Precision : {metrics['precision']:.4f}")
    print(f"  Recall    : {metrics['recall']:.4f}")
    print(f"  F1 Score  : {metrics['f1']:.4f}")
    print(f"  FPR       : {metrics['fpr']:.4f}")

    # 난이도별 분석
    difficulty_stats: dict[str, dict] = {}
    for case in cases:
        d = case["metadata"]["difficulty"]
        if d not in difficulty_stats:
            difficulty_stats[d] = {"total": 0, "correct": 0}
        difficulty_stats[d]["total"] += 1

    for case in cases:
        d = case["metadata"]["difficulty"]
        row = case["input"]["row"]
        expected = case["expected"]["has_violation"]
        violated = check_row_against_rules(row, rules)
        predicted = len(violated) > 0
        if expected == predicted:
            difficulty_stats[d]["correct"] += 1

    print("\n  [난이도별 정확도]")
    for d, stat in sorted(difficulty_stats.items()):
        acc = stat["correct"] / stat["total"] if stat["total"] else 0
        print(f"    {d:8s}: {stat['correct']}/{stat['total']} ({acc:.1%})")

    if failures:
        print(f"\n  [오답 {len(failures)}개]")
        for f in failures[:10]:
            print(f"    [{f['type']}] {f['id']} — {f['note']}")

    # ── 이상치 규칙 골든셋 평가 ───────────────────────────
    if anomaly_path:
        print(f"\n{'=' * 60}")
        print(f"이상치 골든셋: {anomaly_path}")
        print(f"{'=' * 60}")

        atp = afp = afn = atn = 0
        a_failures = []

        with open(anomaly_path, encoding="utf-8") as f:
            a_cases = [json.loads(line) for line in f if line.strip()]

        for case in a_cases:
            expected_exists = case["expected"]["has_anomaly_rule"]
            predicted_correct = check_anomaly_rules(rules, case)

            predicted_exists = expected_exists if predicted_correct else not expected_exists

            if expected_exists and predicted_exists:
                atp += 1
            elif not expected_exists and not predicted_exists:
                atn += 1
            elif not expected_exists and predicted_exists:
                afp += 1
                a_failures.append(
                    {"id": case["id"], "type": "FP", "note": case["metadata"]["note"]}
                )
            else:
                afn += 1
                a_failures.append(
                    {"id": case["id"], "type": "FN", "note": case["metadata"]["note"]}
                )

        a_metrics = compute_metrics(atp, afp, afn, atn)
        print(f"총 케이스: {len(a_cases)}")
        print(f"  TP={atp}, FP={afp}, FN={afn}, TN={atn}")
        print(f"  Precision : {a_metrics['precision']:.4f}")
        print(f"  Recall    : {a_metrics['recall']:.4f}")
        print(f"  F1 Score  : {a_metrics['f1']:.4f}")
        print(f"  FPR       : {a_metrics['fpr']:.4f}")

        if a_failures:
            print(f"\n  [오답 {len(a_failures)}개]")
            for f in a_failures:
                print(f"    [{f['type']}] {f['id']} — {f['note']}")

    # ── 전체 요약 ──────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("전체 요약")
    print(f"{'=' * 60}")
    print(f"  일반 규칙 F1  : {metrics['f1']:.4f}")
    if anomaly_path:
        print(f"  이상치 규칙 F1: {a_metrics['f1']:.4f}")
        overall_f1 = (metrics["f1"] + a_metrics["f1"]) / 2
        print(f"  종합 F1 (평균): {overall_f1:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="골든셋 평가 하니스")
    parser.add_argument("--rules", required=True, help="AI 생성 규칙 JSON 파일 경로")
    parser.add_argument(
        "--golden",
        default=str(Path(__file__).parent / "golden_set_finance_v1.jsonl"),
        help="일반 규칙 골든셋 JSONL 경로",
    )
    parser.add_argument(
        "--anomaly",
        default=str(Path(__file__).parent / "golden_set_finance_anomaly_v1.jsonl"),
        help="이상치 규칙 골든셋 JSONL 경로 (선택)",
    )
    args = parser.parse_args()

    if not Path(args.rules).exists():
        print(f"[ERROR] 규칙 파일 없음: {args.rules}", file=sys.stderr)
        sys.exit(1)

    evaluate(args.rules, args.golden, args.anomaly if Path(args.anomaly).exists() else None)
