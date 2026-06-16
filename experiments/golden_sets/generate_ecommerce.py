"""
이커머스 골든셋 생성 스크립트
============================================
규칙 R1~R9 기반으로 정상/오류/엣지 케이스를 생성하여
golden_set_ecommerce_v1.jsonl 로 저장한다.

규칙:
  R1. order_id     not null      (범용)
  R2. user_email   not null      (범용)
  R3. product_name not null      (범용)
  R4. price        >= 0          (특화, price=0은 엣지)
  R5. quantity     >= 1, 정수     (특화)
  R6. discount_rate 0~100        (특화, 100은 엣지)
  R7. user_email   이메일 형식     (특화)
  R8. status       정해진 5개 값   (특화)
  R9. order_date   미래 아님       (특화)
"""

import json
import os
import random
from datetime import datetime, timedelta

random.seed(42)  # 재현 가능하게 고정

DOMAIN = "ecommerce_orders"
VALID_STATUS = ["pending", "paid", "shipped", "delivered", "cancelled"]
PRODUCTS = [
    "무선 이어폰",
    "키보드",
    "마우스",
    "노트북 거치대",
    "USB 허브",
    "텀블러",
    "백팩",
    "노트",
    "볼펜 세트",
    "독서대",
]
EMAIL_DOMAINS = ["gmail.com", "naver.com", "kakao.com", "daum.net"]


# ── 정상 데이터 한 행 생성 ──
def make_normal_row():
    n = random.randint(1, 99999)
    return {
        "order_id": f"ORD-20260615-{n:05d}",
        "user_email": f"user{n}@{random.choice(EMAIL_DOMAINS)}",
        "product_name": random.choice(PRODUCTS),
        "price": random.choice([9900, 15000, 25000, 39000, 120000]),
        "quantity": random.randint(1, 5),
        "discount_rate": random.choice([0, 5, 10, 15, 20, 30]),
        "order_date": "2026-06-15T14:30:00",
        "status": random.choice(VALID_STATUS),
    }


# ── 케이스 누적용 ──
cases = []
counter = {"normal": 0, "error": 0, "edge": 0}


def add_case(row, has_violation, violated_rules, rule_tested, case_type, difficulty, note):
    counter_key = "error" if case_type == "error_injection" else case_type
    counter[counter_key] += 1
    idx = counter[counter_key]
    cases.append(
        {
            "id": f"ecom_{rule_tested}_{case_type}_{idx:03d}",
            "input": {"domain": DOMAIN, "row": row},
            "expected": {
                "has_violation": has_violation,
                "violated_rules": violated_rules,
            },
            "metadata": {
                "rule_tested": rule_tested,
                "case_type": case_type,
                "difficulty": difficulty,
                "note": note,
            },
        }
    )


# ════════════════════════════════════════════
# 1) 정상 케이스 20개
# ════════════════════════════════════════════
for _ in range(20):
    add_case(make_normal_row(), False, [], "normal", "normal", "easy", "정상 주문")


# ════════════════════════════════════════════
# 2) 오류 케이스 30개 (규칙별 주입)
# ════════════════════════════════════════════
# R1: order_id null
for _ in range(3):
    row = make_normal_row()
    row["order_id"] = None
    add_case(row, True, ["R1"], "R1", "error_injection", "easy", "order_id가 null")

# R2: user_email null
for _ in range(3):
    row = make_normal_row()
    row["user_email"] = None
    add_case(row, True, ["R2"], "R2", "error_injection", "easy", "email이 null")

# R3: product_name null
for _ in range(3):
    row = make_normal_row()
    row["product_name"] = None
    add_case(row, True, ["R3"], "R3", "error_injection", "easy", "상품명이 null")

# R4: price 음수
for _ in range(4):
    row = make_normal_row()
    row["price"] = random.choice([-5000, -100, -39000])
    add_case(row, True, ["R4"], "R4", "error_injection", "easy", "가격이 음수")

# R5: quantity 0 또는 소수
for _ in range(4):
    row = make_normal_row()
    row["quantity"] = random.choice([0, 2.5, -1])
    add_case(row, True, ["R5"], "R5", "error_injection", "easy", "수량이 0/소수/음수")

# R6: discount_rate 범위 초과
for _ in range(4):
    row = make_normal_row()
    row["discount_rate"] = random.choice([150, -10, 200])
    add_case(row, True, ["R6"], "R6", "error_injection", "easy", "할인율 범위 벗어남")

# R7: 이메일 형식 오류
for _ in range(4):
    row = make_normal_row()
    row["user_email"] = random.choice(["usergmail.com", "user@@gmail", "user@", "@gmail.com"])
    add_case(row, True, ["R7"], "R7", "error_injection", "medium", "이메일 형식 오류")

# R8: status 잘못된 값
for _ in range(3):
    row = make_normal_row()
    row["status"] = random.choice(["완료", "unknown", "ORDERED"])
    add_case(row, True, ["R8"], "R8", "error_injection", "easy", "status 비정상 값")

# R9: 미래 날짜
for _ in range(2):
    future = datetime(2026, 6, 15) + timedelta(days=random.randint(10, 100))
    row = make_normal_row()
    row["order_date"] = future.strftime("%Y-%m-%dT%H:%M:%S")
    add_case(row, True, ["R9"], "R9", "error_injection", "medium", "미래 주문일")


# ════════════════════════════════════════════
# 3) 엣지 케이스 10개 (경계값, 도메인 판단 필요)
# ════════════════════════════════════════════
# price = 0 (증정품일 수 있음 → 기본 정상으로 라벨)
for _ in range(3):
    row = make_normal_row()
    row["price"] = 0
    row["product_name"] = "사은품 스티커"
    add_case(row, False, [], "R4", "edge", "hard", "price=0, 증정품 맥락이면 정상")

# discount_rate = 100 (전액 할인 → 기본 정상)
for _ in range(2):
    row = make_normal_row()
    row["discount_rate"] = 100
    add_case(row, False, [], "R6", "edge", "hard", "discount=100%, 전액할인 프로모션이면 정상")

# discount_rate = 0 (경계값, 정상)
for _ in range(2):
    row = make_normal_row()
    row["discount_rate"] = 0
    add_case(row, False, [], "R6", "edge", "medium", "discount=0, 할인 없음 정상")

# quantity = 매우 큰 값 (대량주문, 정상)
for _ in range(2):
    row = make_normal_row()
    row["quantity"] = random.choice([500, 1000])
    add_case(row, False, [], "R5", "edge", "medium", "대량주문, 정상 가능")

# price 매우 큰 값 (고가 상품, 정상)
for _ in range(1):
    row = make_normal_row()
    row["price"] = 50000000
    row["product_name"] = "명품 시계"
    add_case(row, False, [], "R4", "edge", "medium", "고가 상품, 정상")


# ════════════════════════════════════════════
# 저장
# ════════════════════════════════════════════
out_path = os.path.join(os.path.dirname(__file__), "golden_set_ecommerce_v1.jsonl")
with open(out_path, "w", encoding="utf-8") as f:
    for c in cases:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")

# 통계 출력
print(f"✅ 골든셋 생성 완료: {out_path}")
print(f"   총 {len(cases)}개")
print(f"   - 정상(normal): {counter['normal']}개")
print(f"   - 오류(error):  {counter['error']}개")
print(f"   - 엣지(edge):   {counter['edge']}개")
