"""
제조/IoT 도메인 데이터 프로파일링
=================================
두 CSV를 넣고 돌리면 골든셋 설계에 필요한 정보를 출력합니다.

사용법:
    python profile_iot_data.py --data1 ai4i2020.csv --data2 manufacturing_defects.csv

    ※ 파일명이 다르면 실제 파일명으로 바꿔서 실행
"""

import argparse

import numpy as np
import pandas as pd


def profile_dataset(df: pd.DataFrame, name: str):
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    print(f"Shape: {df.shape[0]}행 × {df.shape[1]}컬럼")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nDtypes:\n{df.dtypes.to_string()}")

    # Null counts
    nulls = df.isnull().sum()
    if nulls.sum() > 0:
        print("\nNull counts:")
        print(nulls[nulls > 0].to_string())
    else:
        print("\nNull counts: 없음 (전부 0)")

    # Numeric stats
    print("\nNumeric columns:")
    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col]
        print(
            f"  {col}: min={s.min()}, max={s.max()}, mean={s.mean():.3f}, std={s.std():.3f}, null={s.isnull().sum()}"
        )

    # Categorical stats
    print("\nCategorical/String columns:")
    for col in df.select_dtypes(include=["object", "string", "category"]).columns:
        uniq = df[col].nunique()
        vals = list(df[col].unique()[:10])
        print(f"  {col}: {uniq} unique → {vals}")

    # Cross-column checks (AI4I specific)
    if "Process temperature [K]" in df.columns and "Air temperature [K]" in df.columns:
        violations = (df["Process temperature [K]"] <= df["Air temperature [K]"]).sum()
        print(f"\n[Cross-column] Process temp <= Air temp violations: {violations}/{len(df)}")

    if "Defect Rate" in df.columns and "ProductionVolume" in df.columns:
        zero_prod_with_defect = ((df["ProductionVolume"] == 0) & (df["Defect Rate"] > 0)).sum()
        print(f"\n[Cross-column] Production=0 but Defect>0: {zero_prod_with_defect}/{len(df)}")

    # Value distribution for binary/low-cardinality columns
    print("\nLow-cardinality column distributions:")
    for col in df.columns:
        if df[col].nunique() <= 10:
            print(f"  {col}: {dict(df[col].value_counts())}")

    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data1", required=True, help="AI4I 2020 CSV 경로")
    parser.add_argument("--data2", required=True, help="Manufacturing Defects CSV 경로")
    args = parser.parse_args()

    df1 = pd.read_csv(args.data1)
    df2 = pd.read_csv(args.data2)

    profile_dataset(df1, "Sub-1: AI4I 2020 Predictive Maintenance (Sensor)")
    profile_dataset(df2, "Sub-2: Manufacturing Defects (Process/Quality)")


if __name__ == "__main__":
    main()
