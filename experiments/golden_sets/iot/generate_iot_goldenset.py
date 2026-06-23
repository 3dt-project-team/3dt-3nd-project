"""
제조·IoT 도메인 골든셋 생성기
- Sub-1: AI4I 2020 Predictive Maintenance (Sensor)
- Sub-2: Manufacturing Defects (Process/Quality)

Usage:
    python generate_iot_goldenset.py --data1 ai4i2020.csv --data2 manufacturing_defects.csv --out .
"""

import argparse
import json
import os
import random

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)


def save_jsonl(data, path):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    print(f"  ✅ {len(data)} cases → {path}")


# ============================================================
# SUB-1: AI4I 2020 Predictive Maintenance
# ============================================================


def gen_sensor_general(df):
    cases = []
    cid = 0

    # --- 정상 (9개) ---
    for _, row in df[df["Machine failure"] == 0].sample(3).iterrows():
        cid += 1
        cases.append(
            {
                "id": f"iot1_clean_{cid:03d}",
                "input": {"row": row.to_dict()},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {
                    "note": "Real clean row, no failure",
                    "difficulty": "easy",
                    "domain": "iot_sensor",
                },
            }
        )

    # Edge: Tool wear = 0 (valid, new tool)
    row = df[df["Tool wear [min]"] == 0].sample(1).iloc[0].to_dict()
    cid += 1
    cases.append(
        {
            "id": f"iot1_edge_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Tool wear=0, brand new tool, valid",
                "difficulty": "medium",
                "domain": "iot_sensor",
            },
        }
    )

    # Edge: Tool wear = max (249, valid)
    row = df[df["Tool wear [min]"] == df["Tool wear [min]"].max()].sample(1).iloc[0].to_dict()
    cid += 1
    cases.append(
        {
            "id": f"iot1_edge_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Tool wear at max=249, still valid",
                "difficulty": "medium",
                "domain": "iot_sensor",
            },
        }
    )

    # FP trap: Machine failure=1 (valid data point, NOT a quality violation)
    row = df[df["Machine failure"] == 1].sample(1).iloc[0].to_dict()
    cid += 1
    cases.append(
        {
            "id": f"iot1_fp_trap_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Machine failure=1 is valid observation, NOT data quality violation",
                "difficulty": "hard",
                "domain": "iot_sensor",
            },
        }
    )

    # FP trap: Type='H' (rare but valid)
    row = df[df["Type"] == "H"].sample(1).iloc[0].to_dict()
    cid += 1
    cases.append(
        {
            "id": f"iot1_fp_trap_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Type H is rare (961/10000) but valid",
                "difficulty": "medium",
                "domain": "iot_sensor",
            },
        }
    )

    # FP trap: High torque (near max, valid)
    row = df.sample(1).iloc[0].to_dict()
    row["Torque [Nm]"] = 75.0
    cid += 1
    cases.append(
        {
            "id": f"iot1_fp_trap_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "High torque near max, still valid",
                "difficulty": "hard",
                "domain": "iot_sensor",
            },
        }
    )

    # --- 위반 (9개) ---

    # NULL: Air temperature
    row = df.sample(1).iloc[0].to_dict()
    row["Air temperature [K]"] = None
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["not_null:Air temperature [K]"]},
            "metadata": {
                "note": "NULL air temp (dead sensor)",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        }
    )

    # NULL: Rotational speed
    row = df.sample(1).iloc[0].to_dict()
    row["Rotational speed [rpm]"] = None
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {
                "has_violation": True,
                "violated_rules": ["not_null:Rotational speed [rpm]"],
            },
            "metadata": {
                "note": "NULL rotational speed",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        }
    )

    # CROSS-COLUMN: Process temp <= Air temp (physics violation)
    row = df.sample(1).iloc[0].to_dict()
    row["Air temperature [K]"] = 310.0
    row["Process temperature [K]"] = 305.0
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {
                "has_violation": True,
                "violated_rules": ["cross_column:Process temperature>Air temperature"],
            },
            "metadata": {
                "note": "Process temp < Air temp (thermodynamic impossibility)",
                "difficulty": "medium",
                "domain": "iot_sensor",
            },
        }
    )

    # Negative torque
    row = df.sample(1).iloc[0].to_dict()
    row["Torque [Nm]"] = -5.0
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:Torque [Nm]"]},
            "metadata": {"note": "Negative torque", "difficulty": "easy", "domain": "iot_sensor"},
        }
    )

    # Negative rotational speed
    row = df.sample(1).iloc[0].to_dict()
    row["Rotational speed [rpm]"] = -100
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:Rotational speed [rpm]"]},
            "metadata": {"note": "Negative RPM", "difficulty": "easy", "domain": "iot_sensor"},
        }
    )

    # Invalid Type
    row = df.sample(1).iloc[0].to_dict()
    row["Type"] = "X"
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["in_set:Type"]},
            "metadata": {
                "note": "Invalid product type",
                "difficulty": "medium",
                "domain": "iot_sensor",
            },
        }
    )

    # Tool wear negative
    row = df.sample(1).iloc[0].to_dict()
    row["Tool wear [min]"] = -10
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:Tool wear [min]"]},
            "metadata": {
                "note": "Negative tool wear",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        }
    )

    # Machine failure not 0/1
    row = df.sample(1).iloc[0].to_dict()
    row["Machine failure"] = 3
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["in_set:Machine failure"]},
            "metadata": {
                "note": "Machine failure must be 0 or 1",
                "difficulty": "medium",
                "domain": "iot_sensor",
            },
        }
    )

    # Air temp way out of range (0 Kelvin region)
    row = df.sample(1).iloc[0].to_dict()
    row["Air temperature [K]"] = 50.0
    cid += 1
    cases.append(
        {
            "id": f"iot1_viol_{cid:03d}",
            "input": {"row": row},
            "expected": {"has_violation": True, "violated_rules": ["range:Air temperature [K]"]},
            "metadata": {
                "note": "Air temp 50K is physically impossible for manufacturing",
                "difficulty": "hard",
                "domain": "iot_sensor",
            },
        }
    )

    return cases


def gen_sensor_anomaly(df):
    return [
        {
            "id": "iot1_anom_001",
            "input": {
                "column": "Air temperature [K]",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 300.0,
                    "std": 2.0,
                    "min": 292.3,
                    "max": 309.0,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric sensor, zscore expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_002",
            "input": {
                "column": "Process temperature [K]",
                "method": "iqr",
                "column_profile": {
                    "dtype": "numeric",
                    "q1": 308.5,
                    "q3": 311.5,
                    "min": 301.1,
                    "max": 320.5,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric sensor, IQR expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_003",
            "input": {
                "column": "Rotational speed [rpm]",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 1537.4,
                    "std": 179.4,
                    "min": 887,
                    "max": 2171,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric RPM, zscore expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_004",
            "input": {
                "column": "Torque [Nm]",
                "method": "iqr",
                "column_profile": {
                    "dtype": "numeric",
                    "q1": 33.0,
                    "q3": 47.0,
                    "min": 2.9,
                    "max": 77.2,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric torque, IQR expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_005",
            "input": {
                "column": "Tool wear [min]",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 124.1,
                    "std": 72.1,
                    "min": 0,
                    "max": 249,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric tool wear, zscore expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_006",
            "input": {
                "column": "Type",
                "method": "frequency",
                "column_profile": {
                    "dtype": "categorical",
                    "unique_values": ["L", "M", "H"],
                    "unique_count": 3,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Categorical product type, frequency expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
        # --- traps ---
        {
            "id": "iot1_anom_007",
            "input": {
                "column": "Machine failure",
                "method": "zscore",
                "column_profile": {"dtype": "binary", "unique_values": [0, 1]},
            },
            "expected": {"has_anomaly_rule": False},
            "metadata": {
                "note": "TRAP: binary flag, zscore meaningless",
                "difficulty": "hard",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_008",
            "input": {
                "column": "TWF",
                "method": "iqr",
                "column_profile": {"dtype": "binary", "unique_values": [0, 1]},
            },
            "expected": {"has_anomaly_rule": False},
            "metadata": {
                "note": "TRAP: binary failure flag, IQR meaningless",
                "difficulty": "hard",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_009",
            "input": {
                "column": "UDI",
                "method": "zscore",
                "column_profile": {
                    "dtype": "integer_id",
                    "min": 1,
                    "max": 10000,
                    "unique_ratio": 1.0,
                },
            },
            "expected": {"has_anomaly_rule": False},
            "metadata": {
                "note": "TRAP: sequential ID, zscore meaningless",
                "difficulty": "hard",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_010",
            "input": {
                "column": "HDF",
                "method": "zscore",
                "column_profile": {"dtype": "binary", "unique_values": [0, 1]},
            },
            "expected": {"has_anomaly_rule": False},
            "metadata": {
                "note": "TRAP: binary failure flag, zscore meaningless",
                "difficulty": "hard",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_011",
            "input": {
                "column": "Rotational speed [rpm]",
                "method": "iqr",
                "column_profile": {
                    "dtype": "numeric",
                    "q1": 1420,
                    "q3": 1650,
                    "min": 887,
                    "max": 2171,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric RPM, IQR also expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
        {
            "id": "iot1_anom_012",
            "input": {
                "column": "Torque [Nm]",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 39.9,
                    "std": 9.9,
                    "min": 2.9,
                    "max": 77.2,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric torque, zscore also expected",
                "difficulty": "easy",
                "domain": "iot_sensor",
            },
        },
    ]


# ============================================================
# SUB-2: Manufacturing Defects (Process/Quality)
# ============================================================


def gen_mfg_general(df):
    cases = []
    cid = 0

    # --- 정상 (10개) ---
    for _, row in df.sample(4).iterrows():
        cid += 1
        r = {
            k: (
                round(float(v), 4)
                if isinstance(v, (float, np.floating))
                else int(v)
                if isinstance(v, (np.integer,))
                else v
            )
            for k, v in row.to_dict().items()
        }
        cases.append(
            {
                "id": f"iot2_clean_{cid:03d}",
                "input": {"row": r},
                "expected": {"has_violation": False, "violated_rules": []},
                "metadata": {"note": "Real clean row", "difficulty": "easy", "domain": "iot_mfg"},
            }
        )

    # Edge: DefectRate at min boundary (0.5, valid)
    row = df[df["DefectRate"] < 0.6].sample(1).iloc[0].to_dict()
    r = {
        k: (
            round(float(v), 4)
            if isinstance(v, (float, np.floating))
            else int(v)
            if isinstance(v, (np.integer,))
            else v
        )
        for k, v in row.items()
    }
    cid += 1
    cases.append(
        {
            "id": f"iot2_edge_{cid:03d}",
            "input": {"row": r},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "DefectRate near min, valid",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        }
    )

    # Edge: QualityScore at min boundary (~60, valid)
    row = df[df["QualityScore"] < 61].sample(1).iloc[0].to_dict()
    r = {
        k: (
            round(float(v), 4)
            if isinstance(v, (float, np.floating))
            else int(v)
            if isinstance(v, (np.integer,))
            else v
        )
        for k, v in row.items()
    }
    cid += 1
    cases.append(
        {
            "id": f"iot2_edge_{cid:03d}",
            "input": {"row": r},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "QualityScore near min, valid",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        }
    )

    # FP trap: High DefectRate (near 5, valid range)
    row = df[df["DefectRate"] > 4.8].sample(1).iloc[0].to_dict()
    r = {
        k: (
            round(float(v), 4)
            if isinstance(v, (float, np.floating))
            else int(v)
            if isinstance(v, (np.integer,))
            else v
        )
        for k, v in row.items()
    }
    cid += 1
    cases.append(
        {
            "id": f"iot2_fp_trap_{cid:03d}",
            "input": {"row": r},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "High defect rate but within range",
                "difficulty": "hard",
                "domain": "iot_mfg",
            },
        }
    )

    # FP trap: DeliveryDelay = 5 (max, valid)
    row = df[df["DeliveryDelay"] == 5].sample(1).iloc[0].to_dict()
    r = {
        k: (
            round(float(v), 4)
            if isinstance(v, (float, np.floating))
            else int(v)
            if isinstance(v, (np.integer,))
            else v
        )
        for k, v in row.items()
    }
    cid += 1
    cases.append(
        {
            "id": f"iot2_fp_trap_{cid:03d}",
            "input": {"row": r},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "Max delivery delay but valid",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        }
    )

    # FP trap: SafetyIncidents = 9 (max, valid)
    row = df[df["SafetyIncidents"] == 9].sample(1).iloc[0].to_dict()
    r = {
        k: (
            round(float(v), 4)
            if isinstance(v, (float, np.floating))
            else int(v)
            if isinstance(v, (np.integer,))
            else v
        )
        for k, v in row.items()
    }
    cid += 1
    cases.append(
        {
            "id": f"iot2_fp_trap_{cid:03d}",
            "input": {"row": r},
            "expected": {"has_violation": False, "violated_rules": []},
            "metadata": {
                "note": "High safety incidents but valid",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        }
    )

    # --- 위반 (10개) ---

    row = df.sample(1).iloc[0].to_dict()
    row["ProductionVolume"] = None
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["not_null:ProductionVolume"]},
            "metadata": {
                "note": "NULL production volume",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["ProductionVolume"] = -50
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["range:ProductionVolume"]},
            "metadata": {
                "note": "Negative production volume",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["ProductionCost"] = -1000.0
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["range:ProductionCost"]},
            "metadata": {
                "note": "Negative production cost",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["SupplierQuality"] = 110.0
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["range:SupplierQuality"]},
            "metadata": {
                "note": "SupplierQuality > 100%",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["QualityScore"] = -5.0
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["range:QualityScore"]},
            "metadata": {
                "note": "Negative quality score",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["DefectRate"] = -1.0
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["range:DefectRate"]},
            "metadata": {"note": "Negative defect rate", "difficulty": "easy", "domain": "iot_mfg"},
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["DowntimePercentage"] = 150.0
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["range:DowntimePercentage"]},
            "metadata": {
                "note": "Downtime > 100% impossible",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["EnergyEfficiency"] = -0.5
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["range:EnergyEfficiency"]},
            "metadata": {
                "note": "Negative energy efficiency",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["MaintenanceHours"] = None
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["not_null:MaintenanceHours"]},
            "metadata": {
                "note": "NULL maintenance hours",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        }
    )

    row = df.sample(1).iloc[0].to_dict()
    row["DefectStatus"] = 5
    cid += 1
    cases.append(
        {
            "id": f"iot2_viol_{cid:03d}",
            "input": {
                "row": {
                    k: (
                        round(float(v), 4)
                        if isinstance(v, (float, np.floating))
                        else int(v)
                        if isinstance(v, (np.integer,))
                        else v
                    )
                    for k, v in row.items()
                }
            },
            "expected": {"has_violation": True, "violated_rules": ["in_set:DefectStatus"]},
            "metadata": {
                "note": "DefectStatus must be 0 or 1",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        }
    )

    return cases


def gen_mfg_anomaly(df):
    return [
        {
            "id": "iot2_anom_001",
            "input": {
                "column": "ProductionVolume",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 548.5,
                    "std": 262.4,
                    "min": 100,
                    "max": 999,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric production vol, zscore expected",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_002",
            "input": {
                "column": "ProductionCost",
                "method": "iqr",
                "column_profile": {
                    "dtype": "numeric",
                    "q1": 8500,
                    "q3": 16500,
                    "min": 5000,
                    "max": 20000,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric cost, IQR expected",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_003",
            "input": {
                "column": "DefectRate",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 2.75,
                    "std": 1.31,
                    "min": 0.5,
                    "max": 5.0,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric defect rate, zscore expected",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_004",
            "input": {
                "column": "EnergyConsumption",
                "method": "iqr",
                "column_profile": {
                    "dtype": "numeric",
                    "q1": 2000,
                    "q3": 4000,
                    "min": 1000,
                    "max": 5000,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric energy, IQR expected",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_005",
            "input": {
                "column": "MaintenanceHours",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 11.5,
                    "std": 6.9,
                    "min": 0,
                    "max": 23,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric maintenance hours, zscore expected",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        },
        # --- traps ---
        {
            "id": "iot2_anom_006",
            "input": {
                "column": "DefectStatus",
                "method": "zscore",
                "column_profile": {"dtype": "binary", "unique_values": [0, 1]},
            },
            "expected": {"has_anomaly_rule": False},
            "metadata": {
                "note": "TRAP: binary status, zscore meaningless",
                "difficulty": "hard",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_007",
            "input": {
                "column": "DefectStatus",
                "method": "iqr",
                "column_profile": {"dtype": "binary", "unique_values": [0, 1]},
            },
            "expected": {"has_anomaly_rule": False},
            "metadata": {
                "note": "TRAP: binary status, IQR meaningless",
                "difficulty": "hard",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_008",
            "input": {
                "column": "DeliveryDelay",
                "method": "frequency",
                "column_profile": {
                    "dtype": "ordinal_int",
                    "unique_values": [0, 1, 2, 3, 4, 5],
                    "unique_count": 6,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Ordinal int with few categories, frequency expected",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_009",
            "input": {
                "column": "WorkerProductivity",
                "method": "zscore",
                "column_profile": {
                    "dtype": "numeric",
                    "mean": 90.0,
                    "std": 5.7,
                    "min": 80,
                    "max": 100,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Numeric productivity, zscore expected",
                "difficulty": "easy",
                "domain": "iot_mfg",
            },
        },
        {
            "id": "iot2_anom_010",
            "input": {
                "column": "SafetyIncidents",
                "method": "frequency",
                "column_profile": {
                    "dtype": "ordinal_int",
                    "unique_values": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
                    "unique_count": 10,
                },
            },
            "expected": {"has_anomaly_rule": True},
            "metadata": {
                "note": "Ordinal int, frequency expected for incident spikes",
                "difficulty": "medium",
                "domain": "iot_mfg",
            },
        },
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data1", required=True, help="AI4I 2020 CSV")
    parser.add_argument("--data2", required=True, help="Manufacturing Defects CSV")
    parser.add_argument("--out", default=".", help="Output dir")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    df1 = pd.read_csv(args.data1)
    df2 = pd.read_csv(args.data2)
    print(f"Sensor: {df1.shape}, Mfg: {df2.shape}")

    s_gen = gen_sensor_general(df1)
    s_anom = gen_sensor_anomaly(df1)
    m_gen = gen_mfg_general(df2)
    m_anom = gen_mfg_anomaly(df2)

    save_jsonl(s_gen, os.path.join(args.out, "golden_set_iot_sensor_v1.jsonl"))
    save_jsonl(s_anom, os.path.join(args.out, "golden_set_iot_sensor_anomaly_v1.jsonl"))
    save_jsonl(m_gen, os.path.join(args.out, "golden_set_iot_mfg_v1.jsonl"))
    save_jsonl(m_anom, os.path.join(args.out, "golden_set_iot_mfg_anomaly_v1.jsonl"))

    print(
        f"\nSensor General: {len(s_gen)} (clean {sum(1 for c in s_gen if not c['expected']['has_violation'])} / viol {sum(1 for c in s_gen if c['expected']['has_violation'])})"
    )
    print(
        f"Sensor Anomaly: {len(s_anom)} (true {sum(1 for c in s_anom if c['expected']['has_anomaly_rule'])} / false {sum(1 for c in s_anom if not c['expected']['has_anomaly_rule'])})"
    )
    print(
        f"Mfg General:    {len(m_gen)} (clean {sum(1 for c in m_gen if not c['expected']['has_violation'])} / viol {sum(1 for c in m_gen if c['expected']['has_violation'])})"
    )
    print(
        f"Mfg Anomaly:    {len(m_anom)} (true {sum(1 for c in m_anom if c['expected']['has_anomaly_rule'])} / false {sum(1 for c in m_anom if not c['expected']['has_anomaly_rule'])})"
    )


if __name__ == "__main__":
    main()
