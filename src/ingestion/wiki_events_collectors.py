import json
import sys
import time

import requests
from requests.exceptions import ChunkedEncodingError, RequestException
from sseclient import SSEClient

WIKI_STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
TARGET_WIKIS = {"kowiki", "enwiki"}
MAX_EVENTS = 20
RECONNECT_DELAY_SECONDS = 3

headers = {
    "Accept": "text/event-stream",
    "User-Agent": "3dt-data-quality-project/0.1 (wiki recentchange collector)",
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def iter_wiki_events():
    while True:
        try:
            with requests.get(
                WIKI_STREAM_URL,
                stream=True,
                headers=headers,
                timeout=(10, 60),
            ) as response:
                response.raise_for_status()
                client = SSEClient(response)

                for event in client.events():
                    if event.event != "message":
                        continue

                    try:
                        data = json.loads(event.data)
                    except json.JSONDecodeError:
                        continue

                    if data.get("wiki") in TARGET_WIKIS:
                        yield data

        except (ChunkedEncodingError, RequestException) as exc:
            print(f"Stream connection dropped: {exc}")
            print(f"Reconnecting in {RECONNECT_DELAY_SECONDS} seconds...")
            time.sleep(RECONNECT_DELAY_SECONDS)


print("Wikipedia real-time event collection started...")
print(f"Target wikis: {', '.join(sorted(TARGET_WIKIS))}")

count = 0

for data in iter_wiki_events():
    count += 1

    print("=" * 80)
    print(f"event number: {count}")
    print(f"wiki: {data.get('wiki')}")
    print(f"type: {data.get('type')}")
    print(f"title: {data.get('title')}")
    print(f"user: {data.get('user')}")
    print(f"timestamp: {data.get('timestamp')}")
    print(f"comment: {data.get('comment')}")

    if count >= MAX_EVENTS:
        break
