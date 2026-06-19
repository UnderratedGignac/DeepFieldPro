"""
Poll the ntfy topic for incoming messages from the user's phone.
Usage: .venv\Scripts\python.exe tools\ntfy_listen.py
Send a message to the topic from your ntfy app and it will appear here.
"""

import requests, time, sys, os

TOPIC = "deepfieldpro-elie-haddad"
POLL_URL = f"https://ntfy.sh/{TOPIC}/json?poll=1&since=10m"

print(f"Listening on ntfy topic: {TOPIC}")
print("Send a message from your phone ntfy app now...")
print("(polling every 5 seconds, Ctrl+C to stop)\n")

seen = set()
while True:
    try:
        resp = requests.get(POLL_URL, timeout=10)
        for line in resp.text.strip().splitlines():
            if not line.strip():
                continue
            import json

            msg = json.loads(line)
            mid = msg.get("id", "")
            if mid in seen:
                continue
            seen.add(mid)
            ts = time.strftime("%H:%M:%S", time.localtime(msg.get("time", 0)))
            text = msg.get("message", "")
            title = msg.get("title", "")
            print(f"[{ts}] {title + ': ' if title else ''}{text}")
    except Exception as e:
        print(f"Poll error: {e}")
    time.sleep(5)
