import json

from sseclient import SSEClient as EventSource

url = "https://stream.wikimedia.org/v2/stream/recentchange"
print("[START] 위키피디아 실시간 스트림 연결 시도 중...")

try:
    for event in EventSource(url):
        if event.event == "message":
            try:
                change = json.loads(event.data)

                # 테스트용(canary) 이벤트 제외
                if change.get("meta", {}).get("domain") == "canary":
                    continue

                server = change.get("server_name")
                user = change.get("user")
                comment = change.get("comment", "")

                print(f"[{server}] 유저: {user} | 사유: {comment}")
            except ValueError:
                pass
except KeyboardInterrupt:
    print("\n[STOP] 스트림 수집을 종료합니다.")
