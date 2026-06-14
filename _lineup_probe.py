import requests, json
H = {"User-Agent": "Mozilla/5.0"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

def find_event(league, date_compact, team_substr):
    r = requests.get(f"{BASE}/{league}/scoreboard", headers=H, params={"dates": date_compact}, timeout=15)
    for e in r.json().get("events", []):
        if team_substr.lower() in e.get("name","").lower():
            return e.get("id"), e.get("name")
    return None, None

# 1) Chilean Primera - Coquimbo (finished 2026-06-13) -> does summary have lineups?
eid, name = find_event("chi.1", "20260613", "Coquimbo")
print("chi.1 event:", eid, name)
if eid:
    r = requests.get(f"{BASE}/chi.1/summary", headers=H, params={"event": eid}, timeout=15)
    data = r.json()
    print("summary top keys:", list(data.keys()))
    rosters = data.get("rosters")
    if rosters:
        for ro in rosters:
            team = ro.get("team", {}).get("displayName")
            starters = [p for p in ro.get("roster", []) if p.get("starter")]
            print(f"   {team}: {len(starters)} starters; sample: {[p.get('athlete',{}).get('displayName') for p in starters[:3]]}")
    else:
        print("   NO 'rosters' key. has lineups?:", 'lineup' in json.dumps(data)[:5000].lower())

# 2) A big league upcoming match today to check pre-match lineup availability
print("\n--- EPL/Spain check for any event with rosters today ---")
import datetime
today = datetime.datetime.utcnow().strftime("%Y%m%d")
for lg in ["esp.1","eng.1","ita.1","usa.1","bra.1"]:
    try:
        r = requests.get(f"{BASE}/{lg}/scoreboard", headers=H, params={"dates": today}, timeout=12)
        evs = r.json().get("events", [])
        print(f"  {lg}: {len(evs)} events today")
    except Exception as e:
        print(f"  {lg}: err {e}")
