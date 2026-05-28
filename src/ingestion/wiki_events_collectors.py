import json

import requests
from sseclient import SSEClient

WIKI_STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"

headers = {"Accept": "text/event-stream", "User-Agent": "3dt-data-quality-project/0.1"}

response = requests.get(WIKI_STREAM_URL, stream=True, headers=headers)
client = SSEClient(response)

print("Wikipedia 실시간 이벤트 수신 시작...")

count = 0

for event in client.events():
    if event.event != "message":
        continue

    try:
        data = json.loads(event.data)
    except json.JSONDecodeError:
        continue

    # 한국어 위키만 필터링
    if data.get("wiki") != "kowiki":
        continue

    count += 1

    print("=" * 80)
    print(f"수신 번호: {count}")
    print(f"wiki: {data.get('wiki')}")
    print(f"type: {data.get('type')}")
    print(f"title: {data.get('title')}")
    print(f"user: {data.get('user')}")
    print(f"timestamp: {data.get('timestamp')}")
    print(f"comment: {data.get('comment')}")

    if count >= 20:
        break
