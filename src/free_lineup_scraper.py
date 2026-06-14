"""
free_lineup_scraper.py — free official starting-XI lineups from ESPN.
=====================================================================
Replaces the bot-blocked Sofascore lineup feed. Given a match (home, away, date),
finds the ESPN event and returns the official starting XI for both teams IF they
have been posted (11 confirmed starters per side), else None.

Format matches the predictor's expectation (same as get_predicted_lineup):
    [ {"startXI": [{"player": {"name": "..."}}, ...11...]},   # home
      {"startXI": [{"player": {"name": "..."}}, ...11...]} ]  # away

Entry point:
    get_official_lineups(home_name, away_name, kickoff_date "YYYY-MM-DD") -> list | None
"""

import time
import re
import unicodedata
import requests

from src.free_results_scraper import ESPN_LEAGUES

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
       "Accept": "application/json, text/plain, */*"}
_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# date_compact -> (epoch, index)  ;  index: list of (league, event_id, home_norm, away_norm)
_index_cache = {}
_INDEX_TTL = 900  # 15 min


def _norm(name):
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", str(name).lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    noise = {"fc", "cf", "sc", "cd", "ac", "afc", "club", "deportivo", "de", "the",
             "united", "city", "ii", "u20", "u23", "atletico", "athletic"}
    return " ".join(w for w in n.split() if w and w not in noise)


def _similar(a, b):
    sa, sb = set(_norm(a).split()), set(_norm(b).split())
    if not sa or not sb:
        return 0.0
    if sa == sb:
        return 1.0
    inter = sa & sb
    if not inter:
        # substring fallback for one-word names
        na, nb = _norm(a).replace(" ", ""), _norm(b).replace(" ", "")
        if na and nb and (na in nb or nb in na):
            return 0.7
        return 0.0
    return len(inter) / len(sa | sb) + 0.5


def _build_index(date_compact):
    cached = _index_cache.get(date_compact)
    if cached and (time.time() - cached[0]) < _INDEX_TTL:
        return cached[1]
    index = []
    for lg in ESPN_LEAGUES:
        try:
            r = requests.get(f"{_BASE}/{lg}/scoreboard", headers=_UA,
                             params={"dates": date_compact}, timeout=8)
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
            if hn and an:
                index.append((lg, e.get("id"), hn, an))
    _index_cache[date_compact] = (time.time(), index)
    return index


def _find_event(home, away, date_compact):
    best, best_score = None, 1.2  # require a reasonably strong match
    for lg, eid, hn, an in _build_index(date_compact):
        score = _similar(home, hn) + _similar(away, an)
        if score > best_score:
            best_score = score
            best = (lg, eid)
    return best if best else (None, None)


def get_official_lineups(home_name, away_name, kickoff_date):
    """Return official [home_XI, away_XI] if both posted (11 starters each), else None."""
    date_compact = (kickoff_date or "").replace("-", "")[:8]
    if len(date_compact) != 8:
        return None
    lg, eid = _find_event(home_name, away_name, date_compact)
    if not eid:
        return None
    try:
        r = requests.get(f"{_BASE}/{lg}/summary", headers=_UA,
                         params={"event": eid}, timeout=10)
        rosters = r.json().get("rosters") or []
    except Exception:
        return None
    if len(rosters) != 2:
        return None

    by_team = {}
    for ro in rosters:
        tname = (ro.get("team") or {}).get("displayName", "")
        starters = [p for p in (ro.get("roster") or []) if p.get("starter")]
        xi = [{"player": {"name": (p.get("athlete") or {}).get("displayName", "")}}
              for p in starters if (p.get("athlete") or {}).get("displayName")]
        by_team[tname] = xi

    # Assign rosters to home/away by best name match.
    home_xi = max(by_team.items(), key=lambda kv: _similar(home_name, kv[0]), default=(None, []))[1]
    away_xi = max(by_team.items(), key=lambda kv: _similar(away_name, kv[0]), default=(None, []))[1]

    if len(home_xi) < 11 or len(away_xi) < 11:
        return None  # lineups not fully posted yet
    return [{"startXI": home_xi[:11]}, {"startXI": away_xi[:11]}]


if __name__ == "__main__":
    lu = get_official_lineups("Coquimbo Unido", "O'Higgins", "2026-06-13")
    if lu:
        print("home XI:", [p["player"]["name"] for p in lu[0]["startXI"]])
        print("away XI:", [p["player"]["name"] for p in lu[1]["startXI"]])
    else:
        print("no official lineups found")
