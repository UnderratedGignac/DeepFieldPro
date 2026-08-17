"""
lineup_service.py — Fetches match lineups + enriches with FIFA ratings.
========================================================================
Main entry:
    get_tonight_lineups(date_str=None) -> list[dict]

Each match dict:
{
    "fixture_id": int,
    "home": str,
    "away": str,
    "league": str,
    "kickoff": str,
    "status": str,       # "NS", "LIVE", "FT"
    "lineup_status": str, # "confirmed", "predicted", "unavailable"
    "home_xi": [...],     # list of {name, position, rating}
    "away_xi": [...],     # same
    "home_bench": [...],
    "away_bench": [...],
    "home_rating_avg": float,
    "away_rating_avg": float,
    "home_formation": str,
    "away_formation": str,
}

Uses:
    - ESPN roster API via free_lineup_scraper for confirmed lineups
    - todays_dashboard_state.json for upcoming match list
    - fifa_ratings.py for player ratings (seed DB + ESPN enrichment)
    - SQLite cache in data/lineups_cache.db
"""

import json
import os
import sqlite3
import time
import unicodedata
import re
from datetime import datetime, timezone, timedelta

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
_SRC = os.path.dirname(__file__)
_DATA = os.path.join(_SRC, "..", "data")
_STATE_FILE = os.path.join(_DATA, "todays_dashboard_state.json")
_CACHE_DB = os.path.join(_DATA, "lineups_cache.db")
_PRED_FILE = os.path.join(_DATA, "predictions.json")

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

try:
    from src.free_results_scraper import ESPN_LEAGUES
except ImportError:
    try:
        from free_results_scraper import ESPN_LEAGUES
    except ImportError:
        ESPN_LEAGUES = ["eng.1", "esp.1", "ger.1", "ita.1", "fra.1"]

try:
    from src.fifa_ratings import get_player_info, enrich_from_espn_roster
except ImportError:
    try:
        from fifa_ratings import get_player_info, enrich_from_espn_roster
    except ImportError:
        def get_player_info(name, team=None):
            return {"rating": 0, "position": "", "found": False, "source": "none"}
        def enrich_from_espn_roster(h, a, d):
            return {}

# ── Cache layer ───────────────────────────────────────────────────────────────
_CACHE_TTL = 900  # 15 min

def _init_cache_db():
    conn = sqlite3.connect(_CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lineup_cache (
            fixture_id   TEXT PRIMARY KEY,
            data_json    TEXT,
            fetched_at   REAL
        )
    """)
    conn.commit()
    conn.close()


def _get_cached(fixture_id: str) -> dict | None:
    if not os.path.exists(_CACHE_DB):
        return None
    conn = sqlite3.connect(_CACHE_DB)
    try:
        row = conn.execute(
            "SELECT data_json, fetched_at FROM lineup_cache WHERE fixture_id = ?",
            (str(fixture_id),),
        ).fetchone()
        if row and (time.time() - row[1]) < _CACHE_TTL:
            return json.loads(row[0])
    finally:
        conn.close()
    return None


def _set_cached(fixture_id: str, data: dict):
    _init_cache_db()
    conn = sqlite3.connect(_CACHE_DB)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO lineup_cache (fixture_id, data_json, fetched_at) VALUES (?, ?, ?)",
            (str(fixture_id), json.dumps(data), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


# ── Name normalization ────────────────────────────────────────────────────────
def _norm(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", str(name).lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    noise = {"fc", "cf", "sc", "cd", "ac", "afc", "club", "deportivo", "de",
             "the", "united", "city", "ii", "u20", "u23", "atletico", "athletic"}
    return " ".join(w for w in n.split() if w and w not in noise)


def _similar(a: str, b: str) -> float:
    sa, sb = set(_norm(a).split()), set(_norm(b).split())
    if not sa or not sb:
        return 0.0
    if sa == sb:
        return 1.0
    inter = sa & sb
    if not inter:
        na, nb = _norm(a).replace(" ", ""), _norm(b).replace(" ", "")
        if na and nb and (na in nb or nb in na):
            return 0.7
        return 0.0
    return len(inter) / len(sa | sb) + 0.5


# ── ESPN lineup fetching ──────────────────────────────────────────────────────
_date_index_cache = {}
_DATE_INDEX_TTL = 900

# Top leagues to prioritize for fast ESPN lookups
_TOP_ESPN_LEAGUES = [
    "eng.1", "esp.1", "ger.1", "ita.1", "fra.1",
    "ned.1", "por.1", "sco.1", "tur.1", "bel.1",
    "usa.1", "mex.1", "bra.1", "arg.1",
    "uefa.champions", "uefa.europa", "uefa.europa.conf",
    "fifa.world", "fifa.worldq.uefa", "fifa.worldq.conmebol",
]

def _build_date_index(date_compact: str, leagues: list = None) -> list:
    """Build index of (league, event_id, home, away, status) for a date."""
    lg_key = leagues or _TOP_ESPN_LEAGUES
    cache_key = f"{date_compact}_{','.join(lg_key[:3])}"
    cached = _date_index_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _DATE_INDEX_TTL:
        return cached[1]

    index = []
    for lg in lg_key:
        try:
            r = requests.get(
                f"{_ESPN_BASE}/{lg}/scoreboard",
                headers=_UA, params={"dates": date_compact}, timeout=8,
            )
            if r.status_code != 200:
                continue
            events = r.json().get("events", []) or []
        except Exception:
            continue
        for e in events:
            comp = (e.get("competitions") or [{}])[0]
            cs = comp.get("competitors") or []
            if len(cs) != 2:
                continue
            home = next((c for c in cs if c.get("homeAway") == "home"), None)
            away = next((c for c in cs if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            hn = (home.get("team") or {}).get("displayName")
            an = (away.get("team") or {}).get("displayName")
            status = (comp.get("status") or {}).get("type") or {}
            status_name = status.get("name", "STATUS_SCHEDULED")
            if hn and an:
                index.append((lg, e.get("id"), hn, an, status_name))
    _date_index_cache[cache_key] = (time.time(), index)
    return index


def _find_espn_event(home: str, away: str, date_compact: str) -> tuple:
    """Find ESPN event for a match."""
    best, best_score = None, 1.2
    for lg, eid, hn, an, status in _build_date_index(date_compact):
        score = _similar(home, hn) + _similar(away, an)
        if score > best_score:
            best_score = score
            best = (lg, eid, status, hn, an)
    return best if best else (None, None, None, None, None)


def _fetch_roster(lg: str, eid: str) -> list:
    """Fetch roster data from ESPN summary endpoint."""
    try:
        r = requests.get(
            f"{_ESPN_BASE}/{lg}/summary", headers=_UA, params={"event": eid}, timeout=12,
        )
        return r.json().get("rosters") or []
    except Exception:
        return []


def _parse_roster_to_xi(rosters: list, home_name: str, away_name: str) -> dict:
    """Parse ESPN rosters into structured lineup data with FIFA ratings."""
    result = {
        "home_xi": [], "away_xi": [],
        "home_bench": [], "away_bench": [],
        "home_formation": "—", "away_formation": "—",
        "lineup_status": "unavailable",
    }

    if len(rosters) < 2:
        return result

    # Assign rosters to home/away by name similarity
    by_team = {}
    for ro in rosters:
        tname = (ro.get("team") or {}).get("displayName", "")
        players = []
        for p in (ro.get("roster") or []):
            athlete = p.get("athlete") or {}
            name = athlete.get("displayName", "")
            if not name:
                continue
            is_starter = p.get("starter", False)
            pos = ""
            positions = athlete.get("positions") or []
            if positions:
                pos = (positions[0] or {}).get("abbreviation", "")
            jersey = athlete.get("jersey", "")
            players.append({
                "name": name,
                "position": pos,
                "jersey": jersey,
                "is_starter": is_starter,
                "rating": 0,  # will be enriched below
                "team_espn": tname,
            })
        by_team[tname] = players

    # Match teams
    home_key = max(by_team.keys(), key=lambda k: _similar(home_name, k), default=None)
    away_key = max(
        (k for k in by_team.keys() if k != home_key),
        key=lambda k: _similar(away_name, k), default=None,
    )

    for side, team_key in [("home", home_key), ("away", away_key)]:
        if not team_key or team_key not in by_team:
            continue
        team_players = by_team[team_key]
        team_name_for_lookup = team_key

        starters = [p for p in team_players if p["is_starter"]]
        subs = [p for p in team_players if not p["is_starter"]]

        # Enrich with FIFA ratings
        for p in starters + subs:
            info = get_player_info(p["name"], team_name_for_lookup)
            p["rating"] = info["rating"]
            if not p["position"] and info.get("position"):
                p["position"] = info["position"]

        # Sort starters by position (GK, DEF, MID, FWD)
        pos_order = {"G": 0, "GK": 0, "D": 1, "CB": 1, "LB": 1, "RB": 1,
                     "M": 2, "CM": 2, "CDM": 2, "CAM": 2, "DM": 2,
                     "F": 3, "ST": 3, "CF": 3, "LW": 3, "RW": 3, "FW": 3}
        starters.sort(key=lambda p: pos_order.get(p["position"], 5))

        xi_list = []
        for p in starters[:11]:
            xi_list.append({
                "name": p["name"],
                "position": p["position"],
                "rating": p["rating"],
                "jersey": p.get("jersey", ""),
            })

        bench_list = []
        for p in subs[:12]:
            bench_list.append({
                "name": p["name"],
                "position": p["position"],
                "rating": p["rating"],
                "jersey": p.get("jersey", ""),
            })

        if side == "home":
            result["home_xi"] = xi_list
            result["home_bench"] = bench_list
            result["home_formation"] = _detect_formation(xi_list)
        else:
            result["away_xi"] = xi_list
            result["away_bench"] = bench_list
            result["away_formation"] = _detect_formation(xi_list)

    # Determine lineup status
    if len(result["home_xi"]) >= 11 and len(result["away_xi"]) >= 11:
        result["lineup_status"] = "confirmed"
    elif len(result["home_xi"]) > 0 or len(result["away_xi"]) > 0:
        result["lineup_status"] = "partial"

    return result


def _detect_formation(xi: list) -> str:
    """Detect formation from lineup positions."""
    if len(xi) < 11:
        return "—"

    pos_groups = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
    for p in xi:
        pos = p.get("position", "").upper()
        if pos in ("G", "GK"):
            pos_groups["GK"] += 1
        elif pos in ("D", "CB", "LB", "RB", "LWB", "RWB", "DF"):
            pos_groups["DEF"] += 1
        elif pos in ("M", "CM", "CDM", "CAM", "DM", "AM", "LM", "RM"):
            pos_groups["MID"] += 1
        elif pos in ("F", "ST", "CF", "LW", "RW", "FW", "SS"):
            pos_groups["FWD"] += 1
        else:
            # Guess from position in list
            idx = xi.index(p)
            if idx == 0:
                pos_groups["GK"] += 1
            elif idx <= 4:
                pos_groups["DEF"] += 1
            elif idx <= 7:
                pos_groups["MID"] += 1
            else:
                pos_groups["FWD"] += 1

    d, m, f = pos_groups["DEF"], pos_groups["MID"], pos_groups["FWD"]
    if d + m + f == 10:
        return f"{d}-{m}-{f}"
    return f"{d}-{m}-{f}"


def _compute_avg_rating(xi: list) -> float:
    """Compute average rating of a starting XI."""
    rated = [p["rating"] for p in xi if p.get("rating", 0) > 0]
    return round(sum(rated) / len(rated), 1) if rated else 0.0


# ── Main entry point ──────────────────────────────────────────────────────────
def get_tonight_lineups(date_str: str = None) -> list:
    """
    Get lineups for tonight's matches with FIFA ratings.
    Returns list of match dicts with lineup + rating data.
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_compact = date_str.replace("-", "")

    # Load matches from dashboard state
    matches = []
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                matches = json.load(f)
        except Exception:
            pass

    if not matches:
        return []

    # Filter to today's matches
    today_matches = []
    for m in matches:
        kickoff = m.get("kickoff", "")
        if date_str in kickoff:
            today_matches.append(m)

    if not today_matches:
        # Fallback: show all upcoming
        today_matches = matches[:50]

    # Top leagues to prioritize for ESPN fetch budget
    _TOP_LEAGUES = {
        "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
        "english premier league", "spanish primera", "german bundesliga",
        "uefa champions league", "uefa europa league", "mls",
        "brazilian serie a", "argentine primera", "eredivisie",
        "primeira liga", "scottish premiership", "super lig",
    }

    # Sort to prioritize top leagues for ESPN fetch budget
    def _league_priority(m):
        lg = (m.get('league', '') or '').lower()
        return 0 if lg in _TOP_LEAGUES else 1
    today_matches.sort(key=_league_priority)

    results = []
    _espn_fetch_count = 0
    _MAX_ESPN_FETCHES = 25  # limit ESPN API calls per request to avoid timeout

    for m in today_matches:
        fixture_id = str(m.get("fixture_id", ""))
        match_str = m.get("match", "")
        parts = match_str.split(" vs ")
        if len(parts) != 2:
            continue
        home, away = parts[0].strip(), parts[1].strip()
        league = m.get("league", "")
        kickoff = m.get("kickoff", "")
        status_code = m.get("status_code", "NS")

        # Check cache
        cached = _get_cached(fixture_id)
        if cached:
            cached["fixture_id"] = fixture_id
            cached["league"] = league
            cached["kickoff"] = kickoff
            cached["status"] = status_code
            cached["home"] = home
            cached["away"] = away
            results.append(cached)
            continue

        # Try to fetch from ESPN
        lg, eid, espn_status, espn_home, espn_away = _find_espn_event(
            home, away, date_compact
        )

        match_data = {
            "fixture_id": fixture_id,
            "home": home,
            "away": away,
            "league": league,
            "kickoff": kickoff,
            "status": status_code,
            "lineup_status": "unavailable",
            "home_xi": [],
            "away_xi": [],
            "home_bench": [],
            "away_bench": [],
            "home_rating_avg": 0.0,
            "away_rating_avg": 0.0,
            "home_formation": "—",
            "away_formation": "—",
        }

        if eid and lg and _espn_fetch_count < _MAX_ESPN_FETCHES:
            rosters = _fetch_roster(lg, eid)
            if rosters:
                _espn_fetch_count += 1
                parsed = _parse_roster_to_xi(rosters, home, away)
                match_data.update(parsed)
                match_data["home_rating_avg"] = _compute_avg_rating(parsed["home_xi"])
                match_data["away_rating_avg"] = _compute_avg_rating(parsed["away_xi"])

                # Also enrich the FIFA ratings DB from this roster
                try:
                    enrich_from_espn_roster(espn_home or home, espn_away or away, date_str)
                except Exception:
                    pass

        # Cache the result
        _set_cached(fixture_id, match_data)
        results.append(match_data)

    # Sort: confirmed lineups first, then by kickoff time
    def sort_key(m):
        status_order = {"confirmed": 0, "partial": 1, "unavailable": 2}
        return (status_order.get(m.get("lineup_status", "unavailable"), 2),
                m.get("kickoff", ""))

    results.sort(key=sort_key)
    return results


def get_lineup_for_match(fixture_id: str) -> dict | None:
    """Get cached lineup for a specific match."""
    cached = _get_cached(fixture_id)
    if cached:
        cached["fixture_id"] = fixture_id
    return cached


def refresh_lineups(date_str: str = None) -> dict:
    """Force refresh all lineups (clears cache and re-fetches)."""
    _init_cache_db()
    conn = sqlite3.connect(_CACHE_DB)
    try:
        conn.execute("DELETE FROM lineup_cache")
        conn.commit()
    finally:
        conn.close()

    results = get_tonight_lineups(date_str)
    confirmed = sum(1 for r in results if r.get("lineup_status") == "confirmed")
    return {
        "total_matches": len(results),
        "confirmed_lineups": confirmed,
        "partial_lineups": sum(1 for r in results if r.get("lineup_status") == "partial"),
        "unavailable": sum(1 for r in results if r.get("lineup_status") == "unavailable"),
    }


def get_lineup_stats() -> dict:
    """Stats about the lineup cache."""
    _init_cache_db()
    conn = sqlite3.connect(_CACHE_DB)
    try:
        total = conn.execute("SELECT COUNT(*) FROM lineup_cache").fetchone()[0]
        return {"cached_matches": total}
    finally:
        conn.close()


if __name__ == "__main__":
    print("Fetching tonight's lineups...")
    results = get_tonight_lineups()
    print(f"Found {len(results)} matches\n")
    for m in results[:10]:
        status = m.get("lineup_status", "?")
        h_avg = m.get("home_rating_avg", 0)
        a_avg = m.get("away_rating_avg", 0)
        print(f"  [{status:12s}] {m['home']:25s} vs {m['away']:25s}  "
              f"({m.get('league', '')})  "
              f"H:{h_avg} A:{a_avg}")
        if m.get("home_xi"):
            for p in m["home_xi"][:3]:
                print(f"    {p['name']:30s} {p['position']:5s} {p['rating']:3d}")
