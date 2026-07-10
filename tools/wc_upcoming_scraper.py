"""
wc_upcoming_scraper.py — World Cup upcoming fixture injector from Pinnacle + Stair AI.

Pulls upcoming FIFA World Cup matches directly from:
  1. Pinnacle API (sharp_odds_history + live fetch) — fixture list + sharp odds
  2. Stair AI /schedule endpoint — Polymarket mapping + kickoff times
  3. Injects into odds_stream.db so the daemon can evaluate PINNACLE_STEAM bets

WHY: Betarabia typically lists WC games only 12-24h before kickoff.
This scraper runs at each daemon sweep and ensures the system has WC fixtures
from Pinnacle so steam detection starts accumulating snapshots immediately.

Usage:  .venv/Scripts/python.exe tools/wc_upcoming_scraper.py [--dry-run]
        Also importable: from tools.wc_upcoming_scraper import inject_wc_upcoming
"""

import os
import sys
import sqlite3
import time
import datetime
import json
import re
import logging

logger = logging.getLogger("wc_scraper")

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_ODDS_DB = os.path.join(_ROOT, "data", "odds_stream.db")
_COMPLETED_DB = os.path.join(_ROOT, "data", "deepfield_browser_data", "completed_fixtures.db")

_PIN_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
_PIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "x-api-key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
}

try:
    import requests as _requests
except ImportError:
    _requests = None


# ─── Pinnacle fetch ────────────────────────────────────────────────────────────

def _fetch_pinnacle_wc_live():
    """
    Fetch upcoming WC fixtures from Pinnacle using the existing feed module.
    Returns list of dicts with keys: fixture_id, home, away, league, starts_ts, h_dec, d_dec, a_dec
    """
    try:
        sys.path.insert(0, _ROOT)
        from src.pinnacle_feed import fetch_1x2_snapshot
        snap = fetch_1x2_snapshot()
        results = []
        for item in snap:
            lg = item.get("league", "")
            if "world cup" not in lg.lower() and "fifa" not in lg.lower():
                continue
            # Skip special markets (Bookings, Corners etc)
            home = item.get("home_team", "")
            away = item.get("away_team", "")
            if "(" in home or "(" in away:
                continue
            results.append({
                "fixture_id": f"wc_{item['match_key']}",
                "home": home,
                "away": away,
                "league": lg,
                "starts_ts": item.get("starts_ts"),  # already a Unix float
                "h_dec": item.get("h_dec"),
                "d_dec": item.get("d_dec"),
                "a_dec": item.get("a_dec"),
            })
        return results
    except Exception as e:
        logger.warning("Pinnacle live fetch failed: %s", e)
        return []


def _get_pinnacle_from_history():
    """Fallback: pull recent WC entries from sharp_odds_history."""
    if not os.path.exists(_COMPLETED_DB):
        return []
    try:
        conn = sqlite3.connect(_COMPLETED_DB, timeout=10)
        ts_max = conn.execute("SELECT MAX(ts) FROM sharp_odds_history").fetchone()[0]
        if not ts_max:
            conn.close()
            return []
        rows = conn.execute(
            """
            SELECT home_team, away_team, league, selection, decimal_odds, starts_ts
            FROM sharp_odds_history
            WHERE ts >= ? AND (league LIKE '%World Cup%' OR league LIKE '%FIFA%')
            ORDER BY home_team, away_team, selection
            """,
            (ts_max - 600,),
        ).fetchall()
        conn.close()

        _sel_to_odds_key = {"home": "h_dec", "draw": "d_dec", "away": "a_dec"}
        by_match = {}
        for home, away, league, sel, dec_odds, starts_ts in rows:
            key = f"{home}|{away}"
            if key not in by_match:
                by_match[key] = {"home": home, "away": away, "league": league, "starts_ts": starts_ts}
            odds_key = _sel_to_odds_key.get(str(sel).strip().lower())
            if odds_key:  # never store odds under 'home'/'away' — that clobbers team names
                by_match[key][odds_key] = dec_odds

        import zlib

        result = []
        for k, v in by_match.items():
            # zlib.crc32, not hash(): str hash is salted per process, so the
            # same match would get a new fixture_id every restart and
            # INSERT OR REPLACE would accumulate duplicate rows.
            result.append({
                "fixture_id": f"wch_{zlib.crc32(k.encode('utf-8')) & 0xFFFFFFFF}",
                "home": v["home"], "away": v["away"], "league": v["league"],
                "starts_ts": v.get("starts_ts"),
                "h_dec": v.get("h_dec"), "d_dec": v.get("d_dec"), "a_dec": v.get("a_dec"),
            })
        return result
    except Exception as e:
        logger.warning("History fallback failed: %s", e)
        return []


# ─── Stair AI / Polymarket mapping ────────────────────────────────────────────

def _get_stair_schedule():
    """Pull WC fixture schedule from Stair AI (for kickoff times + fixture IDs)."""
    if _requests is None:
        return {}

    env_path = os.path.join(_ROOT, ".env")
    api_key = os.environ.get("STAIR_AI_API_KEY", "")
    if not api_key and os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("STAIR_AI_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
    if not api_key:
        return {}

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    try:
        # Get the WC 2026 season fixture list
        r = _requests.get(
            "https://stair-ai.com/api/v1/data/fixtures",
            params={"season_id": "26618", "limit": 100},
            headers=headers, timeout=15,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        fixtures = data if isinstance(data, list) else data.get("data", [])
        result = {}
        for f in fixtures:
            fid = str(f.get("fixture_id", ""))
            if fid:
                result[fid] = {
                    "home": f.get("home_team", ""),
                    "away": f.get("away_team", ""),
                    "kickoff": f.get("kickoff_time", ""),
                }
        return result
    except Exception as e:
        logger.debug("Stair AI schedule fetch failed: %s", e)
        return {}


# ─── Injection ────────────────────────────────────────────────────────────────

def inject_wc_upcoming(days_ahead=7, dry_run=False, verbose=True):
    """
    Main entry point. Fetches upcoming WC fixtures from Pinnacle and injects
    into odds_stream.db.  Returns count of fixtures injected.
    """
    fixtures = _fetch_pinnacle_wc_live()
    if not fixtures:
        if verbose:
            print("[WC SCRAPER] Live fetch failed, trying history fallback...")
        fixtures = _get_pinnacle_from_history()

    if not fixtures:
        if verbose:
            print("[WC SCRAPER] No WC fixtures available from any source.")
        return 0

    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)
    now_ts = time.time()
    now_iso = datetime.datetime.utcnow().isoformat() + "+00:00"

    to_insert_fixtures = []
    to_insert_markets = []

    for fix in fixtures:
        starts_ts = fix.get("starts_ts")
        if starts_ts:
            ko_dt = datetime.datetime.utcfromtimestamp(starts_ts)
            ko_date = ko_dt.date()
            if ko_date < today or ko_date > cutoff:
                continue
            kickoff_iso = ko_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            kickoff_date = ko_dt.strftime("%Y-%m-%d")
        else:
            # Unknown date, skip
            continue

        fid = fix["fixture_id"]
        home = fix["home"]
        away = fix["away"]
        league = fix.get("league", "FIFA World Cup")
        h_dec = fix.get("h_dec")
        d_dec = fix.get("d_dec")
        a_dec = fix.get("a_dec")

        if verbose:
            # Guard each leg independently — history rows can carry partial
            # odds (e.g. home only), and formatting None crashes the sweep.
            _parts = [
                f"{lbl}={val:.3f}"
                for lbl, val in (("H", h_dec), ("D", d_dec), ("A", a_dec))
                if val is not None
            ]
            edge_str = " ".join(_parts) if _parts else "no odds"
            print(f"[WC SCRAPER] {home} vs {away} ({kickoff_date}) — {edge_str}")

        to_insert_fixtures.append((
            fid, home, away, kickoff_iso, kickoff_date,
            "FIFA_WC_2026", "FIFA World Cup", now_iso,
        ))

        if h_dec:
            to_insert_markets.append((f"{fid}-h", fid, "Match Result", home, h_dec, None, None, None, now_iso))
        if d_dec:
            to_insert_markets.append((f"{fid}-d", fid, "Match Result", "X", d_dec, None, None, None, now_iso))
        if a_dec:
            to_insert_markets.append((f"{fid}-a", fid, "Match Result", away, a_dec, None, None, None, now_iso))

    if not to_insert_fixtures:
        if verbose:
            print("[WC SCRAPER] No upcoming WC fixtures in the next 7 days.")
        return 0

    if dry_run:
        if verbose:
            print(f"[WC SCRAPER] Dry run: {len(to_insert_fixtures)} fixtures would be inserted.")
        return len(to_insert_fixtures)

    conn = sqlite3.connect(_ODDS_DB, timeout=15)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fixture "
            "(fixture_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, "
            "kickoff_time TEXT, kickoff_date TEXT, league_id TEXT, tournament_name TEXT, scraped_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS market "
            "(market_id TEXT PRIMARY KEY, fixture_id TEXT, market_name TEXT, selection_name TEXT, "
            "raw_odds REAL, prop_player TEXT, prop_type TEXT, prop_line REAL, scraped_at TEXT)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO fixture "
            "(fixture_id, home_team, away_team, kickoff_time, kickoff_date, league_id, tournament_name, scraped_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            to_insert_fixtures,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO market "
            "(market_id, fixture_id, market_name, selection_name, raw_odds, prop_player, prop_type, prop_line, scraped_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            to_insert_markets,
        )
        conn.commit()
        if verbose:
            print(
                f"[WC SCRAPER] Injected {len(to_insert_fixtures)} WC fixtures "
                f"+ {len(to_insert_markets)} market rows into odds_stream.db"
            )
    finally:
        conn.close()

    return len(to_insert_fixtures)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    n = inject_wc_upcoming(days_ahead=7, dry_run=dry)
    print(f"Done: {n} WC fixtures processed.")
