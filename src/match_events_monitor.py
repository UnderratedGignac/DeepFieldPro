"""
match_events_monitor.py — Live WC match event tracker (goals, cards, HT/FT).

Polls ESPN live scores every 30s for in-progress WC matches and tracks all
significant events: goals, red cards, yellow cards, penalties, half-time,
and full-time. Events are stored in data/match_events.json and surfaced
via the /arena/api/match_events endpoint.

This is complementary to redcard_monitor.py (which focuses on the betting
edge calculation). This module focuses on comprehensive event logging for
the monitoring dashboard.
"""

import os
import json
import time
import threading
import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVENTS_FILE = os.path.join(_ROOT, "data", "match_events.json")
_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; DeepFieldPro/1.0)"}

# Event type IDs from ESPN API
_GOAL_TYPES = {"goal", "penalty - goal", "penalty goal", "own goal"}
_CARD_TYPES = {"yellow card", "red card", "straight red", "second yellow"}
_STATUS_MAP = {
    "STATUS_IN_PROGRESS": "LIVE",
    "STATUS_HALFTIME": "HT",
    "STATUS_FULL_TIME": "FT",
    "STATUS_FINAL": "FT",
    "STATUS_SCHEDULED": "SCH",
    "STATUS_POSTPONED": "PPD",
}

_lock = threading.Lock()
_running = False


def _load_events() -> dict:
    try:
        with open(_EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"matches": {}, "updated_at": None}


def _save_events(data: dict):
    with _lock:
        data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        with open(_EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def _espn_scoreboard():
    try:
        r = requests.get(f"{_ESPN_BASE}/scoreboard", headers=_UA, timeout=8)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception:
        return []


def _espn_summary(event_id: str) -> dict:
    try:
        r = requests.get(
            f"{_ESPN_BASE}/summary",
            headers=_UA,
            params={"event": event_id},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def _classify_event(detail: dict) -> str:
    """Return event category: goal / own_goal / yellow / red / penalty_miss / other."""
    t = (detail.get("type", {}).get("text") or "").lower()
    if "own goal" in t:
        return "own_goal"
    if "goal" in t:
        return "goal"
    if "red" in t or "straight red" in t or "second yellow" in t:
        return "red_card"
    if "yellow" in t:
        return "yellow_card"
    if "penalty" in t and "goal" not in t:
        return "penalty_miss"
    return "other"


def scan_live_matches():
    """Single pass: update event log for all live WC matches."""
    events_data = _load_events()
    scoreboard = _espn_scoreboard()

    for ev in scoreboard:
        event_id = ev.get("id", "")
        status_name = ev.get("status", {}).get("type", {}).get("name", "")
        status = _STATUS_MAP.get(status_name, status_name)
        clock = ev.get("status", {}).get("displayClock", "")

        comps = ev.get("competitions", [{}])
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})

        home_name = home.get("team", {}).get("displayName", "?")
        away_name = away.get("team", {}).get("displayName", "?")
        home_abbrev = home.get("team", {}).get("abbreviation", "HOM")
        away_abbrev = away.get("team", {}).get("abbreviation", "AWY")
        home_score = int(home.get("score", 0) or 0)
        away_score = int(away.get("score", 0) or 0)
        match_name = f"{home_name} vs {away_name}"

        # Init match record if new
        if event_id not in events_data["matches"]:
            events_data["matches"][event_id] = {
                "match": match_name,
                "home": home_name,
                "away": away_name,
                "home_abbrev": home_abbrev,
                "away_abbrev": away_abbrev,
                "status": status,
                "clock": clock,
                "score": f"{home_score}-{away_score}",
                "events": [],
                "seen_event_ids": [],
            }

        match_rec = events_data["matches"][event_id]
        match_rec["status"] = status
        match_rec["clock"] = clock
        match_rec["score"] = f"{home_score}-{away_score}"

        # Only fetch play-by-play for live/HT matches to reduce API calls
        if status not in ("LIVE", "HT"):
            continue

        summary = _espn_summary(event_id)
        seen = set(match_rec.get("seen_event_ids", []))

        for comp_data in summary.get("competitions", []):
            for detail in comp_data.get("details", []):
                detail_id = str(detail.get("id") or detail.get("sequenceNumber") or "")
                if detail_id and detail_id in seen:
                    continue

                category = _classify_event(detail)
                if category == "other":
                    continue

                team = detail.get("team", {})
                athlete = {}
                athletes = detail.get("athletesInvolved", [])
                if athletes:
                    athlete = athletes[0]

                event_rec = {
                    "id": detail_id,
                    "category": category,
                    "minute": detail.get("clock", {}).get("displayValue", "?"),
                    "team": team.get("displayName", "?"),
                    "team_abbrev": team.get("abbreviation", "?"),
                    "player": athlete.get("displayName", ""),
                    "score_after": f"{home_score}-{away_score}",
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                }

                match_rec["events"].append(event_rec)
                if detail_id:
                    seen.add(detail_id)

                # Log to console for important events
                if category in ("goal", "own_goal", "red_card"):
                    icon = {"goal": "⚽", "own_goal": "🔴 OG", "red_card": "🟥"}.get(category, "•")
                    print(
                        f"[EVENTS] {icon} {match_name} {event_rec['minute']} — "
                        f"{event_rec['player']} ({event_rec['team']}) "
                        f"[{home_score}-{away_score}]"
                    )

        match_rec["seen_event_ids"] = list(seen)
        match_rec["events"] = match_rec["events"][-100:]  # keep last 100 events per match

    # Purge finished matches older than 24h from memory (keep file lean)
    cutoff = time.time() - 86400
    stale = [
        eid for eid, m in events_data["matches"].items()
        if m.get("status") == "FT"
    ]
    for eid in stale[:-5]:  # keep last 5 completed matches for reference
        events_data["matches"].pop(eid, None)

    _save_events(events_data)


def get_live_matches() -> list:
    """Return all tracked match records sorted by live-first."""
    data = _load_events()
    matches = list(data.get("matches", {}).values())
    order = {"LIVE": 0, "HT": 1, "SCH": 2, "FT": 3, "PPD": 4}
    matches.sort(key=lambda m: order.get(m.get("status"), 5))
    return matches


def get_match_events(event_id: str = None) -> list:
    """Return events for a specific match, or all events if no ID given."""
    data = _load_events()
    if event_id:
        return data.get("matches", {}).get(event_id, {}).get("events", [])
    all_events = []
    for m in data.get("matches", {}).values():
        for e in m.get("events", []):
            all_events.append({**e, "match": m["match"]})
    all_events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return all_events[:50]


def start_monitor(interval: int = 30):
    """Start the match event monitor as a background daemon thread."""
    global _running
    if _running:
        return
    _running = True

    def _loop():
        print("[EVENTS] Match event monitor started — polling ESPN every 30s")
        while _running:
            try:
                scan_live_matches()
            except Exception as e:
                print(f"[EVENTS] scan error: {e}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, name="match-events", daemon=True)
    t.start()


def stop_monitor():
    global _running
    _running = False
