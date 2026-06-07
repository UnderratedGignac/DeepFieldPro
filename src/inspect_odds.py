import requests

API_KEY = "4ae9f07e1ae1f775050015c50037a71d"
HEADERS = {"x-apisports-key": API_KEY}
BASE = "https://v3.football.api-sports.io"

r = requests.get(f"{BASE}/odds", headers=HEADERS, params={"fixture": 1528284})
data = r.json()
bookmakers = data.get("response", [])
if bookmakers:
    bets = bookmakers[0].get("bookmakers", [{}])[0].get("bets", [])
    for b in bets[:30]:
        print(f"Market: {b.get('name')}")
        for v in b.get("values")[:3]:
            print(f"  Value: {v}")
else:
    print("No bookmakers found.")
