"""Test Sofascore API with different approaches."""

import sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

date = "2026-06-17"
url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

print("=== Test 0: curl_cffi (Chrome TLS impersonation) ===")
try:
    from curl_cffi import requests as curl_requests

    r = curl_requests.get(url, headers=HEADERS, impersonate="chrome120", timeout=20)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        events = data.get("events", [])
        finished = [
            e for e in events if (e.get("status") or {}).get("type") == "finished"
        ]
        print(f"Total events: {len(events)}, finished: {len(finished)}")
        for e in finished[:5]:
            h = (e.get("homeTeam") or {}).get("name", "?")
            a = (e.get("awayTeam") or {}).get("name", "?")
            hs = (e.get("homeScore") or {}).get("current", "?")
            as_ = (e.get("awayScore") or {}).get("current", "?")
            print(f"  {h} {hs}-{as_} {a}")
    else:
        print(f"Body: {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print()
print("=== Test 1: httpx with HTTP/2 ===")
try:
    import httpx

    with httpx.Client(http2=True, timeout=20, follow_redirects=True) as client:
        r = client.get(url, headers=HEADERS)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            events = data.get("events", [])
            finished = [
                e for e in events if (e.get("status") or {}).get("type") == "finished"
            ]
            print(f"Total events: {len(events)}, finished: {len(finished)}")
            for e in finished[:3]:
                h = (e.get("homeTeam") or {}).get("name", "?")
                a = (e.get("awayTeam") or {}).get("name", "?")
                hs = (e.get("homeScore") or {}).get("current", "?")
                as_ = (e.get("awayScore") or {}).get("current", "?")
                print(f"  {h} {hs}-{as_} {a}")
        else:
            print(f"Body: {r.text[:300]}")
except Exception as e:
    print(f"Error: {e}")

print()
print("=== Test 2: requests with session ===")
try:
    import requests

    s = requests.Session()
    # First visit the main page to get cookies
    s.get(
        "https://www.sofascore.com/",
        headers={"User-Agent": HEADERS["User-Agent"]},
        timeout=10,
    )
    r = s.get(url, headers=HEADERS, timeout=15)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        events = data.get("events", [])
        finished = [
            e for e in events if (e.get("status") or {}).get("type") == "finished"
        ]
        print(f"Total events: {len(events)}, finished: {len(finished)}")
    else:
        print(f"Body: {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print()
print("=== Test 3: sofascore.app mobile API ===")
try:
    import requests

    app_url = f"https://api.sofascore.app/api/v1/sport/football/scheduled-events/{date}"
    r = requests.get(app_url, headers=HEADERS, timeout=15)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        events = data.get("events", [])
        finished = [
            e for e in events if (e.get("status") or {}).get("type") == "finished"
        ]
        print(f"Total: {len(events)} events, {len(finished)} finished")
        for e in finished[:3]:
            h = (e.get("homeTeam") or {}).get("name", "?")
            a = (e.get("awayTeam") or {}).get("name", "?")
            hs = (e.get("homeScore") or {}).get("current", "?")
            as_ = (e.get("awayScore") or {}).get("current", "?")
            print(f"  {h} {hs}-{as_} {a}")
    else:
        print(f"Body: {r.text[:300]}")
except Exception as e:
    print(f"Error: {e}")
