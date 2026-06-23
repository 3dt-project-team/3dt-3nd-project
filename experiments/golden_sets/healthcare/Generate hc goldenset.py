"""
Healthcare Domain Golden Set Generator
- Sub-1: Clinical Vital Signs (mdsajjadullah/synthetic-medical-ehr-dataset-10k)
- Sub-2: Healthcare Billing & Admin (prasad22/healthcare-dataset)

Output: 4 JSONL files (general + anomaly for each sub-domain)
Usage: python generate_hc_goldenset.py --data1 full_dataset.csv --data2 healthcare_dataset.csv --out ./golden_sets/
"""

import argparse
import json
import os
import random

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)


# ============================================================
# SUB-1: Clinical Vital Signs
# ============================================================


def generate_clinical_general(df: pd.DataFrame) -> list:
    """
    일반 규칙 골든셋 (25 cases)
    - 정상행 ~13개 / 위반행 ~12개 (균형)
    - 규칙 유형: not_null, range, in_set, regex, cross_column, edge_case
    """
    cases = []
    case_id = 0

    # --- 정상 케이스 (13개) ---

    # 1-4. 다양한 조건의 정상행 샘플링
    for _, row in df.sample(4).iterrows():
        case_id += 1
        cases.append(
            {
                "id": f"hc1_clean_{case_id:03d}",
                "input": {"row": row.to_dict()},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {
                    "note": "Real clean row from dataset",
                    "difficulty": "easy",
                    "domain": "healthcare_clinical",
                },
            }
        )

    # 5. 경계값: systolic=93 (min근처, 유효)
    row = df.sample(1).iloc[0].to_dict()
    row["systolic_bp"] = 93
    row["diastolic_bp"] = 55
    case_id += 1
    cases.append(
        {
            "id": f"hc1_edge_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Low but valid BP values",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 6. 경계값: bmi=15.0 (최저, 유효)
    row = df.sample(1).iloc[0].to_dict()
    row["bmi"] = 15.0
    case_id += 1
    cases.append(
        {
            "id": f"hc1_edge_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "BMI at dataset minimum, still valid",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 7. 경계값: adherence_pct=100 (최대, 유효)
    row = df.sample(1).iloc[0].to_dict()
    row["adherence_pct"] = 100
    case_id += 1
    cases.append(
        {
            "id": f"hc1_edge_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Perfect adherence, valid",
                "difficulty": "easy",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 8. 경계값: heart_rate=48 (낮지만 운동선수 가능, 유효)
    row = df.sample(1).iloc[0].to_dict()
    row["heart_rate"] = 48
    case_id += 1
    cases.append(
        {
            "id": f"hc1_edge_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Low heart rate (athletic bradycardia), valid",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 9. severity=Severe + outcome=Deceased (극단적이지만 정상 조합)
    row = df[df["severity"] == "Severe"].sample(1).iloc[0].to_dict()
    row["outcome"] = "Deceased"
    case_id += 1
    cases.append(
        {
            "id": f"hc1_edge_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Severe+Deceased combo, valid clinical scenario",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 10-11. False positive trap: 높은 cholesterol + 높은 BMI (위반 아님)
    for i in range(2):
        row = df.sample(1).iloc[0].to_dict()
        row["cholesterol_mg_dl"] = 295 + i * 5
        row["bmi"] = 42.0 + i * 0.5
        case_id += 1
        cases.append(
            {
                "id": f"hc1_fp_trap_{case_id:03d}",
                "input": {"row": row},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {
                    "note": "High but within-range values, NOT a violation",
                    "difficulty": "hard",
                    "domain": "healthcare_clinical",
                },
            }
        )

    # 12-13. False positive trap: Non-binary gender (유효한 카테고리)
    for _ in range(2):
        row = df[df["gender"] == "Non-binary"].sample(1).iloc[0].to_dict()
        case_id += 1
        cases.append(
            {
                "id": f"hc1_fp_trap_{case_id:03d}",
                "input": {"row": row},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {
                    "note": "Non-binary gender is valid category",
                    "difficulty": "medium",
                    "domain": "healthcare_clinical",
                },
            }
        )

    # --- 위반 케이스 (12개) ---

    # 14. systolic_bp = NULL
    row = df.sample(1).iloc[0].to_dict()
    row["systolic_bp"] = None
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["not_null:systolic_bp"]},
            "metadata": {
                "note": "NULL systolic BP",
                "difficulty": "easy",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 15. diastolic_bp = NULL
    row = df.sample(1).iloc[0].to_dict()
    row["diastolic_bp"] = None
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["not_null:diastolic_bp"]},
            "metadata": {
                "note": "NULL diastolic BP",
                "difficulty": "easy",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 16. heart_rate = NULL
    row = df.sample(1).iloc[0].to_dict()
    row["heart_rate"] = None
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["not_null:heart_rate"]},
            "metadata": {
                "note": "NULL heart rate",
                "difficulty": "easy",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 17. CROSS-COLUMN: systolic <= diastolic (의학적 절대 명제 위반)
    row = df.sample(1).iloc[0].to_dict()
    row["systolic_bp"] = 80
    row["diastolic_bp"] = 95
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {
                "has_violation": True,
                "violated_rules": ["cross_column:systolic_bp>diastolic_bp"],
            },
            "metadata": {
                "note": "Systolic < Diastolic (medical impossibility)",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 18. CROSS-COLUMN: systolic == diastolic (pulse pressure = 0)
    row = df.sample(1).iloc[0].to_dict()
    row["systolic_bp"] = 110
    row["diastolic_bp"] = 110
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {
                "has_violation": True,
                "violated_rules": ["cross_column:systolic_bp>diastolic_bp"],
            },
            "metadata": {
                "note": "Systolic == Diastolic (zero pulse pressure)",
                "difficulty": "hard",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 19. heart_rate 음수
    row = df.sample(1).iloc[0].to_dict()
    row["heart_rate"] = -5
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:heart_rate"]},
            "metadata": {
                "note": "Negative heart rate",
                "difficulty": "easy",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 20. bmi 음수
    row = df.sample(1).iloc[0].to_dict()
    row["bmi"] = -2.5
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:bmi"]},
            "metadata": {
                "note": "Negative BMI",
                "difficulty": "easy",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 21. adherence_pct > 100
    row = df.sample(1).iloc[0].to_dict()
    row["adherence_pct"] = 115
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:adherence_pct"]},
            "metadata": {
                "note": "Adherence > 100%",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 22. ICD10 형식 위반 (regex)
    row = df.sample(1).iloc[0].to_dict()
    row["icd10_code"] = "ZZZ99"
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["regex:icd10_code"]},
            "metadata": {
                "note": "Invalid ICD10 format",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 23. severity 잘못된 카테고리
    row = df.sample(1).iloc[0].to_dict()
    row["severity"] = "Critical"
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["in_set:severity"]},
            "metadata": {
                "note": "Invalid severity category",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 24. gender 잘못된 값
    row = df.sample(1).iloc[0].to_dict()
    row["gender"] = "Unknown"
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["in_set:gender"]},
            "metadata": {
                "note": "Invalid gender category",
                "difficulty": "medium",
                "domain": "healthcare_clinical",
            },
        }
    )

    # 25. cholesterol 음수
    row = df.sample(1).iloc[0].to_dict()
    row["cholesterol_mg_dl"] = -50
    case_id += 1
    cases.append(
        {
            "id": f"hc1_viol_{case_id:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:cholesterol_mg_dl"]},
            "metadata": {
                "note": "Negative cholesterol",
                "difficulty": "easy",
                "domain": "healthcare_clinical",
            },
        }
    )

    return cases


def generate_clinical_anomaly(df: pd.DataFrame) -> list:
    """이상치 골든셋 (10 cases)"""
    cases = []

    anomaly_specs = [
        # (column, method, column_profile_overrides, expected, note)
        (
            "systolic_bp",
            "zscore",
            {"dtype": "numeric", "mean": 145.7, "std": 25.0, "min": 92, "max": 200},
            True,
            "Numeric vital sign, zscore anomaly expected",
        ),
        (
            "systolic_bp",
            "iqr",
            {"dtype": "numeric", "q1": 125, "q3": 167, "min": 92, "max": 200},
            True,
            "Numeric vital sign, IQR anomaly expected",
        ),
        (
            "heart_rate",
            "zscore",
            {"dtype": "numeric", "mean": 75.1, "std": 14.0, "min": 48, "max": 106},
            True,
            "Numeric heart rate, zscore expected",
        ),
        (
            "bmi",
            "iqr",
            {"dtype": "numeric", "q1": 22.0, "q3": 34.0, "min": 15.0, "max": 43.2},
            True,
            "Numeric BMI, IQR expected",
        ),
        (
            "cholesterol_mg_dl",
            "zscore",
            {"dtype": "numeric", "mean": 212.0, "std": 45.0, "min": 123, "max": 301},
            True,
            "Numeric cholesterol, zscore expected",
        ),
        (
            "adherence_pct",
            "frequency",
            {"dtype": "numeric", "min": 5, "max": 100, "unique_ratio": 0.096},
            True,
            "Bounded numeric, frequency anomaly for clusters",
        ),
        # --- dtype traps ---
        (
            "adverse_outcome",
            "zscore",
            {"dtype": "binary", "unique_values": [0, 1], "value_counts": {"0": 7000, "1": 3000}},
            False,
            "TRAP: binary column, zscore meaningless",
        ),
        (
            "adverse_outcome",
            "iqr",
            {"dtype": "binary", "unique_values": [0, 1]},
            False,
            "TRAP: binary column, IQR meaningless",
        ),
        (
            "gender",
            "zscore",
            {"dtype": "categorical", "unique_values": ["Male", "Female", "Non-binary"]},
            False,
            "TRAP: categorical column, zscore inapplicable",
        ),
        (
            "severity",
            "iqr",
            {"dtype": "categorical", "unique_values": ["Mild", "Moderate", "Severe"]},
            False,
            "TRAP: categorical ordinal, IQR not directly applicable",
        ),
    ]

    for i, (col, method, profile, expected, note) in enumerate(anomaly_specs):
        cases.append(
            {
                "id": f"hc1_anom_{i + 1:03d}",
                "input": {"column": col, "method": method, "column_profile": profile},
                "expected": {"has_anomaly_rule": expected},
                "metadata": {
                    "note": note,
                    "difficulty": "easy" if expected else "hard",
                    "domain": "healthcare_clinical",
                },
            }
        )

    return cases


# ============================================================
# SUB-2: Healthcare Billing & Admin
# ============================================================


def generate_billing_general(df: pd.DataFrame) -> list:
    """
    일반 규칙 골든셋 (22 cases)
    - 정상행 ~11개 / 위반행 ~11개 (균형)
    """
    cases = []
    case_id = 0

    # Parse dates for manipulation
    df["Date of Admission"] = pd.to_datetime(df["Date of Admission"])
    df["Discharge Date"] = pd.to_datetime(df["Discharge Date"])

    def row_to_serializable(row_dict):
        """Convert datetime/numpy types to JSON-safe types"""
        out = {}
        for k, v in row_dict.items():
            if isinstance(v, pd.Timestamp):
                out[k] = v.strftime("%Y-%m-%d")
            elif isinstance(v, (np.integer,)):
                out[k] = int(v)
            elif isinstance(v, (np.floating,)):
                out[k] = round(float(v), 2)
            else:
                out[k] = v
        return out

    # --- 정상 케이스 (11개) ---

    # 1-4. 정상 데이터 (clean billing > 0)
    clean = df[df["Billing Amount"] > 0].sample(4)
    for _, row in clean.iterrows():
        case_id += 1
        cases.append(
            {
                "id": f"hc2_clean_{case_id:03d}",
                "input": {"row": row_to_serializable(row.to_dict())},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {
                    "note": "Real clean row",
                    "difficulty": "easy",
                    "domain": "healthcare_billing",
                },
            }
        )

    # 5. 경계값: Billing Amount 매우 낮지만 양수
    row = df[df["Billing Amount"] > 0].sample(1).iloc[0].to_dict()
    row["Billing Amount"] = 0.50
    case_id += 1
    cases.append(
        {
            "id": f"hc2_edge_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Very low but positive billing",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 6. 경계값: 당일 입퇴원 (Admission == Discharge)
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    row["Date of Admission"] = pd.Timestamp("2023-06-15")
    row["Discharge Date"] = pd.Timestamp("2023-06-15")
    case_id += 1
    cases.append(
        {
            "id": f"hc2_edge_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Same-day discharge, valid",
                "difficulty": "hard",
                "domain": "healthcare_billing",
            },
        }
    )

    # 7. Age=13 (min값, 유효)
    row = df[df["Age"] == 13].sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    case_id += 1
    cases.append(
        {
            "id": f"hc2_edge_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Young patient age=13, valid",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 8-9. FP trap: 높은 Billing Amount (유효)
    for amt in [50000.0, 52000.0]:
        row = df.sample(1).iloc[0].to_dict()
        row["Billing Amount"] = amt
        case_id += 1
        cases.append(
            {
                "id": f"hc2_fp_trap_{case_id:03d}",
                "input": {"row": row_to_serializable(row)},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {
                    "note": "High billing but valid",
                    "difficulty": "hard",
                    "domain": "healthcare_billing",
                },
            }
        )

    # 10-11. FP trap: 다양한 Blood Type (유효)
    for bt in ["AB-", "O-"]:
        row = df[df["Blood Type"] == bt].sample(1).iloc[0].to_dict()
        row["Billing Amount"] = abs(row["Billing Amount"])
        case_id += 1
        cases.append(
            {
                "id": f"hc2_fp_trap_{case_id:03d}",
                "input": {"row": row_to_serializable(row)},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {
                    "note": f"Rare blood type {bt}, still valid",
                    "difficulty": "medium",
                    "domain": "healthcare_billing",
                },
            }
        )

    # --- 위반 케이스 (11개) ---

    # 12. REAL dirty data: Billing Amount 음수
    neg_rows = df[df["Billing Amount"] < 0]
    if len(neg_rows) > 0:
        row = neg_rows.sample(1).iloc[0].to_dict()
        case_id += 1
        cases.append(
            {
                "id": f"hc2_viol_{case_id:03d}",
                "input": {"row": row_to_serializable(row)},
                "expected": {"has_violation": True, "violated_rules": ["range:Billing Amount"]},
                "metadata": {
                    "note": "REAL negative billing from dataset",
                    "difficulty": "easy",
                    "domain": "healthcare_billing",
                },
            }
        )

    # 13. Billing Amount = 0
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = 0.0
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["range:Billing Amount"]},
            "metadata": {
                "note": "Zero billing amount",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 14. Billing Amount = NULL
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = None
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["not_null:Billing Amount"]},
            "metadata": {
                "note": "NULL billing amount",
                "difficulty": "easy",
                "domain": "healthcare_billing",
            },
        }
    )

    # 15. Age = NULL
    row = df.sample(1).iloc[0].to_dict()
    row["Age"] = None
    row["Billing Amount"] = abs(row["Billing Amount"]) if row["Billing Amount"] else 1000
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["not_null:Age"]},
            "metadata": {"note": "NULL age", "difficulty": "easy", "domain": "healthcare_billing"},
        }
    )

    # 16. Age 음수
    row = df.sample(1).iloc[0].to_dict()
    row["Age"] = -3
    row["Billing Amount"] = abs(row["Billing Amount"])
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["range:Age"]},
            "metadata": {
                "note": "Negative age",
                "difficulty": "easy",
                "domain": "healthcare_billing",
            },
        }
    )

    # 17. 퇴원일 < 입원일 (시계열 역전)
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    row["Date of Admission"] = pd.Timestamp("2023-08-20")
    row["Discharge Date"] = pd.Timestamp("2023-08-15")
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {
                "has_violation": True,
                "violated_rules": ["cross_column:Discharge Date>=Date of Admission"],
            },
            "metadata": {
                "note": "Discharge before admission (date reversal)",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 18. Admission Type 잘못된 값
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    row["Admission Type"] = "Routine"
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["in_set:Admission Type"]},
            "metadata": {
                "note": "Invalid admission type",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 19. Gender 잘못된 값
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    row["Gender"] = "Other"
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["in_set:Gender"]},
            "metadata": {
                "note": "Invalid gender for this dataset",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 20. Test Results 잘못된 값
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    row["Test Results"] = "Pending"
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["in_set:Test Results"]},
            "metadata": {
                "note": "Invalid test result category",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 21. Blood Type 잘못된 값
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    row["Blood Type"] = "C+"
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["in_set:Blood Type"]},
            "metadata": {
                "note": "Invalid blood type",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    # 22. Age > 120 (비현실적)
    row = df.sample(1).iloc[0].to_dict()
    row["Billing Amount"] = abs(row["Billing Amount"])
    row["Age"] = 150
    case_id += 1
    cases.append(
        {
            "id": f"hc2_viol_{case_id:03d}",
            "input": {"row": row_to_serializable(row)},
            "expected": {"has_violation": True, "violated_rules": ["range:Age"]},
            "metadata": {
                "note": "Unrealistic age > 120",
                "difficulty": "medium",
                "domain": "healthcare_billing",
            },
        }
    )

    return cases


def generate_billing_anomaly(df: pd.DataFrame) -> list:
    """이상치 골든셋 (8 cases)"""
    cases = []

    anomaly_specs = [
        (
            "Billing Amount",
            "zscore",
            {"dtype": "numeric", "mean": 25539.3, "std": 14211.5, "min": -2008.5, "max": 52764.3},
            True,
            "Numeric billing, zscore anomaly expected",
        ),
        (
            "Billing Amount",
            "iqr",
            {"dtype": "numeric", "q1": 13241.2, "q3": 37820.5, "min": -2008.5, "max": 52764.3},
            True,
            "Numeric billing, IQR expected",
        ),
        (
            "Age",
            "zscore",
            {"dtype": "numeric", "mean": 51.5, "std": 22.0, "min": 13, "max": 89},
            True,
            "Numeric age, zscore expected",
        ),
        (
            "Medical Condition",
            "frequency",
            {
                "dtype": "categorical",
                "unique_values": [
                    "Cancer",
                    "Obesity",
                    "Diabetes",
                    "Asthma",
                    "Hypertension",
                    "Arthritis",
                ],
                "unique_count": 6,
            },
            True,
            "Categorical condition, frequency anomaly for rare conditions",
        ),
        (
            "Admission Type",
            "frequency",
            {
                "dtype": "categorical",
                "unique_values": ["Urgent", "Emergency", "Elective"],
                "unique_count": 3,
            },
            True,
            "Categorical admission type, frequency expected",
        ),
        # --- dtype traps ---
        (
            "Room Number",
            "iqr",
            {"dtype": "integer_id", "min": 101, "max": 500, "unique_ratio": 0.72},
            False,
            "TRAP: Room number is ID-like, IQR meaningless",
        ),
        (
            "Gender",
            "zscore",
            {"dtype": "categorical", "unique_values": ["Male", "Female"]},
            False,
            "TRAP: categorical gender, zscore inapplicable",
        ),
        (
            "Blood Type",
            "iqr",
            {
                "dtype": "categorical",
                "unique_values": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
            },
            False,
            "TRAP: categorical blood type, IQR inapplicable",
        ),
    ]

    for i, (col, method, profile, expected, note) in enumerate(anomaly_specs):
        cases.append(
            {
                "id": f"hc2_anom_{i + 1:03d}",
                "input": {"column": col, "method": method, "column_profile": profile},
                "expected": {"has_anomaly_rule": expected},
                "metadata": {
                    "note": note,
                    "difficulty": "easy" if expected else "hard",
                    "domain": "healthcare_billing",
                },
            }
        )

    return cases


# ============================================================
# MAIN
# ============================================================


def save_jsonl(data: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    print(f"  ✅ Saved {len(data)} cases → {path}")


def main():
    parser = argparse.ArgumentParser(description="Healthcare Golden Set Generator")
    parser.add_argument("--data1", required=True, help="Path to clinical CSV (full_dataset.csv)")
    parser.add_argument(
        "--data2", required=True, help="Path to billing CSV (healthcare_dataset.csv)"
    )
    parser.add_argument("--out", default="./golden_sets", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # Load data
    print("Loading datasets...")
    df1 = pd.read_csv(args.data1)
    df2 = pd.read_csv(args.data2)
    print(f"  Clinical: {df1.shape}")
    print(f"  Billing:  {df2.shape}")

    # Generate Sub-1: Clinical
    print("\n[Sub-1] Clinical Vital Signs")
    clinical_general = generate_clinical_general(df1)
    clinical_anomaly = generate_clinical_anomaly(df1)
    save_jsonl(clinical_general, os.path.join(args.out, "golden_set_hc_clinical_v1.jsonl"))
    save_jsonl(clinical_anomaly, os.path.join(args.out, "golden_set_hc_clinical_anomaly_v1.jsonl"))

    # Generate Sub-2: Billing
    print("\n[Sub-2] Healthcare Billing")
    billing_general = generate_billing_general(df2)
    billing_anomaly = generate_billing_anomaly(df2)
    save_jsonl(billing_general, os.path.join(args.out, "golden_set_hc_billing_v1.jsonl"))
    save_jsonl(billing_anomaly, os.path.join(args.out, "golden_set_hc_billing_anomaly_v1.jsonl"))

    # Summary
    print("\n" + "=" * 60)
    print("HEALTHCARE GOLDEN SET GENERATION COMPLETE")
    print("=" * 60)
    print(
        f"  Clinical General:  {len(clinical_general)} cases (clean {sum(1 for c in clinical_general if not c['expected']['has_violation'])} / violation {sum(1 for c in clinical_general if c['expected']['has_violation'])})"
    )
    print(
        f"  Clinical Anomaly:  {len(clinical_anomaly)} cases (true {sum(1 for c in clinical_anomaly if c['expected']['has_anomaly_rule'])} / false {sum(1 for c in clinical_anomaly if not c['expected']['has_anomaly_rule'])})"
    )
    print(
        f"  Billing General:   {len(billing_general)} cases (clean {sum(1 for c in billing_general if not c['expected']['has_violation'])} / violation {sum(1 for c in billing_general if c['expected']['has_violation'])})"
    )
    print(
        f"  Billing Anomaly:   {len(billing_anomaly)} cases (true {sum(1 for c in billing_anomaly if c['expected']['has_anomaly_rule'])} / false {sum(1 for c in billing_anomaly if not c['expected']['has_anomaly_rule'])})"
    )
    print(f"\nOutput directory: {args.out}")


if __name__ == "__main__":
    main()
