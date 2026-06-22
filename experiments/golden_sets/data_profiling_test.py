import glob
import os

import pandas as pd

folder = r"C:\Users\EL048\Desktop\online retail 2 uci"

# 폴더(하위 폴더 포함)에서 엑셀/CSV 자동 탐색
found = (
    glob.glob(os.path.join(folder, "**", "*.xlsx"), recursive=True)
    + glob.glob(os.path.join(folder, "**", "*.xls"), recursive=True)
    + glob.glob(os.path.join(folder, "**", "*.csv"), recursive=True)
)
print("찾은 파일:", found)

path = found[0]  # 첫 번째 파일 사용
print("로딩 중:", path)

if path.lower().endswith(".csv"):
    df = pd.read_csv(path, encoding="latin-1")
else:
    df = pd.read_excel(path, sheet_name=0)
# 시트 2개면: df = pd.concat(pd.read_excel("...", sheet_name=None).values(), ignore_index=True)

print("=== 기본 ===")
print("행/열:", df.shape)
print(df.dtypes)

print("\n=== 결측 비율(%) ===")
print((df.isnull().mean() * 100).round(2))

print("\n=== Quantity ===")
print(df["Quantity"].describe())
print("음수:", (df["Quantity"] < 0).sum(), " / 초대량(>1000):", (df["Quantity"] > 1000).sum())

print("\n=== Price ===")
print(df["Price"].describe())
print("0 이하:", (df["Price"] <= 0).sum())

print("\n=== 취소거래(Invoice C 시작) ===")
print(df["Invoice"].astype(str).str.startswith("C").sum())

print("\n=== 비표준 StockCode (숫자5자리 아님) ===")
codes = df["StockCode"].astype(str)
print(codes[~codes.str.match(r"^\d{5}$")].value_counts().head(10))

print("\n=== Country 상위 ===")
print(df["Country"].value_counts().head(10))

print("\n=== 날짜 범위 / 완전중복 ===")
print(df["InvoiceDate"].min(), "~", df["InvoiceDate"].max())
print("중복 행:", df.duplicated().sum())
