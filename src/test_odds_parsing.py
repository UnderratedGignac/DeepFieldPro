import json

with open("data/betarabia_api_responses.json", "r") as f:
    responses = json.load(f)

events_by_id = {}
markets_by_event = {}

# 1. Parse events
for resp in responses:
    data = resp.get("data", {})
    url = resp.get("url", "")
    if not isinstance(data, dict):
        continue
    if "events" in data:
        raw_events = data["events"]
        if isinstance(raw_events, dict):
            event_list = list(raw_events.values())
        elif isinstance(raw_events, list):
            event_list = raw_events
        else:
            continue
            
        for ev in event_list:
            if not isinstance(ev, dict):
                continue
            ev_id = str(ev.get("id"))
            if not ev_id:
                continue
            
            teams = ev.get("teams", {})
            if isinstance(teams, dict):
                home = teams.get("home", "")
                away = teams.get("away", "")
            else:
                home = ev.get("team_home", "")
                away = ev.get("team_away", "")
                
            events_by_id[ev_id] = {
                "fixture_id": ev_id,
                "home_team": home,
                "away_team": away,
                "kickoff_time": ev.get("date_start", "")
            }

print(f"Parsed {len(events_by_id)} events.")

# 2. Parse odds from events and odds tables
for resp in responses:
    data = resp.get("data", {})
    if not isinstance(data, dict):
        continue
        
    # Extract odds from events directly (new format)
    if "events" in data:
        raw_events = data["events"]
        event_list = list(raw_events.values()) if isinstance(raw_events, dict) else raw_events
        for ev in event_list:
            if not isinstance(ev, dict):
                continue
            ev_id = str(ev.get("id"))
            if ev_id not in events_by_id:
                continue
            
            if ev_id not in markets_by_event:
                markets_by_event[ev_id] = []
                
            main_odds = ev.get("main_odds", {})
            if not isinstance(main_odds, dict):
                continue
                
            # Parse main (1X2)
            for odd_id, odd_obj in main_odds.get("main", {}).items():
                val = odd_obj.get("odd_value")
                code = odd_obj.get("odd_code", "")
                name = odd_obj.get("team_name", "")
                uid = odd_obj.get("unique_id", odd_id)
                markets_by_event[ev_id].append({
                    "market_id": uid,
                    "market_name": "Match Result",
                    "selection_name": name,
                    "raw_odds": val,
                    "odd_code": code
                })
                
            # Parse bothscore (BTTS)
            for odd_id, odd_obj in main_odds.get("bothscore", {}).items():
                val = odd_obj.get("odd_value")
                code = odd_obj.get("odd_code", "")
                name = odd_obj.get("team_name", "")
                uid = odd_obj.get("unique_id", odd_id)
                markets_by_event[ev_id].append({
                    "market_id": uid,
                    "market_name": "Both teams to score",
                    "selection_name": name,
                    "raw_odds": val,
                    "odd_code": code
                })
                
            # Parse total (Over/Under)
            for odd_id, odd_obj in main_odds.get("total", {}).items():
                val = odd_obj.get("odd_value")
                code = odd_obj.get("odd_code", "")
                uid = odd_obj.get("unique_id", odd_id)
                line = odd_obj.get("additional_value_raw") or odd_obj.get("additional_value", "")
                name = f"Total {odd_obj.get('team_name', '')} {str(line).strip()}"
                markets_by_event[ev_id].append({
                    "market_id": uid,
                    "market_name": "Total Goals",
                    "selection_name": name,
                    "raw_odds": val,
                    "odd_code": code
                })

total_markets = sum(len(m) for m in markets_by_event.values())
print(f"Parsed {total_markets} market odds from events.")
# Print a sample of 2 events and their parsed markets
sampled = 0
for ev_id, mkts in markets_by_event.items():
    if len(mkts) > 0 and sampled < 2:
        ev_info = events_by_id[ev_id]
        print(f"\nMatch: {ev_info['home_team']} vs {ev_info['away_team']} (ID: {ev_id})")
        for m in mkts[:5]:
            print(f"  Market: {m['market_name']} | Selection: {m['selection_name']} | Odds: {m['raw_odds']} | Code: {m['odd_code']}")
        sampled += 1
