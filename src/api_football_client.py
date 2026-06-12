import os
import requests
import datetime
import time
import logging
import sqlite3
from typing import List, Dict, Any, Optional

# Ensure we can import from src
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.dfp_config import settings

logger = logging.getLogger(__name__)

API_KEY = settings.API_FOOTBALL_KEY or "4ae9f07e1ae1f775050015c50037a71d"
API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_ODDS = os.path.join(DATA_DIR, "odds_stream.db")

def get_fixtures_from_espn() -> List[Dict[str, Any]]:
    """
    Fetches today's and tomorrow's fixtures from ESPN's public (free, no-key) API.
    Used as a fallback when API-Football is rate-limited.
    Returns fixtures in the same format as get_todays_fixtures_api().
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    formatted = []
    seen_matches: dict = {}

    for delta in [0, 1]:  # today + tomorrow UTC
        date_str = (now_utc + datetime.timedelta(days=delta)).strftime("%Y%m%d")
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
        try:
            r = requests.get(url, params={"dates": date_str}, timeout=15)
            if r.status_code != 200:
                continue
            data = r.json()
            for ev in data.get("events", []):
                comps = ev.get("competitions", [])
                if not comps:
                    continue
                c = comps[0]
                competitors = c.get("competitors", [])
                home_obj = next((t for t in competitors if t.get("homeAway") == "home"), {})
                away_obj = next((t for t in competitors if t.get("homeAway") == "away"), {})
                home_name = home_obj.get("team", {}).get("displayName", "")
                away_name = away_obj.get("team", {}).get("displayName", "")
                if not home_name or not away_name:
                    continue

                kt = c.get("date", "")
                status_name = c.get("status", {}).get("type", {}).get("name", "STATUS_SCHEDULED")
                # Map ESPN status names to our short codes
                status_map = {
                    "STATUS_SCHEDULED": "NS",
                    "STATUS_IN_PROGRESS": "1H",
                    "STATUS_HALFTIME": "HT",
                    "STATUS_FINAL": "FT",
                    "STATUS_FULL_TIME": "FT",
                    "STATUS_POSTPONED": "PST",
                    "STATUS_CANCELED": "CANC",
                    "STATUS_SUSPENDED": "SUSP",
                }
                status_short = status_map.get(status_name, "NS")

                home_score = home_obj.get("score")
                away_score = away_obj.get("score")
                league_name = ev.get("season", {}).get("displayName", "ESPN")
                fixture_id = ev.get("id", f"espn_{date_str}_{len(formatted)}")

                item = {
                    "fixture": {
                        "id": fixture_id,
                        "date": kt,
                        "status": {"short": status_short},
                        "home_score": home_score,
                        "away_score": away_score,
                    },
                    "league": {"name": league_name},
                    "teams": {
                        "home": {"name": home_name},
                        "away": {"name": away_name},
                    }
                }
                m_key = f"{home_name} vs {away_name}".lower()
                if m_key not in seen_matches:
                    seen_matches[m_key] = len(formatted)
                    formatted.append(item)
                else:
                    formatted[seen_matches[m_key]] = item
        except Exception as e:
            logger.error(f"[ESPN] Error fetching fixtures for {date_str}: {e}")

    logger.info(f"[ESPN] Retrieved {len(formatted)} fixtures")
    return formatted


def get_todays_fixtures_api() -> List[Dict[str, Any]]:
    """
    Fetches today's and tomorrow's fixtures.
    Priority chain:
      1. API-Football (paid tier)  — skipped if daily rate limit hit
      2. ESPN public API           — free, no key, ~hundreds of matches
      3. Betarabia odds_stream.db  — always merged in as supplement
    All results are de-duped and returned in a unified format.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today = now_utc.strftime("%Y-%m-%d")
    tomorrow = (now_utc + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    formatted: List[Dict[str, Any]] = []
    seen_matches: dict = {}  # "home vs away" -> index in formatted
    api_rate_limited = False

    # ── Tier 1: API-Football ─────────────────────────────────────────────────
    for date_str in [today, tomorrow]:
        url = f"{API_BASE}/fixtures"
        params = {"date": date_str}
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                # Detect daily rate-limit error even when HTTP 200
                errors = data.get("errors", {})
                if isinstance(errors, dict) and errors.get("requests"):
                    logger.warning(f"[API-Football] Rate-limit hit for {date_str}: {errors['requests']}")
                    api_rate_limited = True
                    break  # No point trying the next date either

                for f in data.get("response", []):
                    home_name = f["teams"]["home"]["name"]
                    away_name = f["teams"]["away"]["name"]
                    status = f["fixture"]["status"]["short"]
                    kt = f["fixture"]["date"]
                    item = {
                        "fixture": {
                            "id": f["fixture"]["id"],
                            "date": kt,
                            "status": {"short": status},
                            "home_score": f["goals"]["home"],
                            "away_score": f["goals"]["away"],
                        },
                        "league": {"name": f["league"]["name"]},
                        "teams": {
                            "home": {"name": home_name},
                            "away": {"name": away_name},
                        }
                    }
                    m_key = f"{home_name} vs {away_name}".lower()
                    if m_key not in seen_matches:
                        seen_matches[m_key] = len(formatted)
                        formatted.append(item)
                    else:
                        formatted[seen_matches[m_key]] = item
        except Exception as e:
            logger.error(f"[API-Football] Error fetching fixtures for {date_str}: {e}")

    # ── Tier 2: ESPN (free, no key) — used when API-Football is rate-limited ─
    if api_rate_limited or not formatted:
        logger.info("[Fixture] Falling back to ESPN free API...")
        espn_fixtures = get_fixtures_from_espn()
        for ef in espn_fixtures:
            m_key = f"{ef['teams']['home']['name']} vs {ef['teams']['away']['name']}".lower()
            if m_key not in seen_matches:
                seen_matches[m_key] = len(formatted)
                formatted.append(ef)
            # Don't override API-Football data if we have it

    # ── Tier 3: Betarabia odds_stream.db — always merged in ─────────────────
    db_fixtures = get_fixtures_from_db()
    for db_f in db_fixtures:
        match_name = f"{db_f['teams']['home']['name']} vs {db_f['teams']['away']['name']}".lower()
        # Smart status detection for Betarabia fixtures
        try:
            kt = db_f["fixture"]["date"]
            ko = datetime.datetime.fromisoformat(kt.replace("Z", "+00:00"))
            elapsed_min = (now_utc - ko).total_seconds() / 60.0
            if elapsed_min > 95:   db_f["fixture"]["status"]["short"] = "FT"
            elif elapsed_min > 45: db_f["fixture"]["status"]["short"] = "2H"
            elif elapsed_min > 0:  db_f["fixture"]["status"]["short"] = "1H"
            else:                  db_f["fixture"]["status"]["short"] = "NS"
        except:
            pass

        if match_name in seen_matches:
            idx = seen_matches[match_name]
            # Betarabia has accurate kickoff times — prefer them
            formatted[idx]["fixture"]["date"] = db_f["fixture"]["date"]
            formatted[idx]["fixture"]["status"] = db_f["fixture"]["status"]
        else:
            formatted.append(db_f)
            seen_matches[match_name] = len(formatted) - 1

    logger.info(f"[Fixture] Total fixtures assembled: {len(formatted)} (API-Football rate-limited: {api_rate_limited})")
    return formatted

def get_fixtures_from_db() -> List[Dict[str, Any]]:
    """Reads fixtures from odds_stream.db (Betarabia)."""
    fixtures = []
    if os.path.exists(DB_ODDS):
        try:
            conn = sqlite3.connect(DB_ODDS)
            cur = conn.cursor()
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            today_prefix = now_utc.strftime("%Y-%m-%d")
            tomorrow_prefix = (now_utc + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            
            cur.execute(
                "SELECT fixture_id, home_team, away_team, kickoff_time, tournament_name FROM fixture "
                "WHERE kickoff_time LIKE ? OR kickoff_time LIKE ?", (f"{today_prefix}%", f"{tomorrow_prefix}%")
            )
            for fid, h, a, kt, lgn in cur.fetchall():
                fixtures.append({
                    "fixture": {
                        "id": fid,
                        "date": kt,
                        "status": {"short": "NS"}, # Initial status, will be updated by caller
                        "home_score": None,
                        "away_score": None
                    },
                    "league": {"name": lgn or "Betarabia"},
                    "teams": {
                        "home": {"name": h},
                        "away": {"name": a}
                    }
                })
            conn.close()
        except Exception as e:
            logger.error(f"Error reading fixtures from DB: {e}")
    return fixtures

def get_fixture_lineups_api(fixture_id: int) -> List[Dict[str, Any]]:
    """Fetches lineups for a single fixture from API-Football."""
    url = f"{API_BASE}/fixtures/lineups"
    params = {"fixture": fixture_id}
    
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("response", [])
    except Exception as e:
        logger.error(f"Error fetching lineups for {fixture_id}: {e}")
        
    return []

def get_fixture_lineups_batch_api(fixture_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """
    Fetches lineups for multiple fixtures. 
    Note: API-Football doesn't support batch lineup requests, 
    so we loop (respecting rate limits).
    """
    results = {}
    for fid in fixture_ids:
        lineups = get_fixture_lineups_api(fid)
        if lineups:
            results[fid] = lineups
        time.sleep(1) # Rate limit padding
    return results

def get_finished_matches_api(date_str: str) -> List[Dict[str, Any]]:
    """Fetches finished matches for a specific date from API-Football."""
    url = f"{API_BASE}/fixtures"
    params = {"date": date_str, "status": "FT"}
    
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("response", [])
    except Exception as e:
        logger.error(f"Error fetching finished matches for {date_str}: {e}")
        
    return []

def get_fixture_stats_api(fixture_id: int) -> Optional[Dict[str, Any]]:
    """Fetches statistics for a fixture from API-Football."""
    url = f"{API_BASE}/fixtures/statistics"
    params = {"fixture": fixture_id}
    
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"Error fetching stats for {fixture_id}: {e}")
        
    return None
