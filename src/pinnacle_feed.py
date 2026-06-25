"""
pinnacle_feed.py — Live Pinnacle 1X2 odds feed.

Polls Pinnacle's guest API every POLL_INTERVAL seconds and writes snapshots to
sharp_odds_history in completed_fixtures.db. No API key required.

Usage (standalone): .venv/Scripts/python.exe src/pinnacle_feed.py
Usage (daemon):     from src.pinnacle_feed import start_feed_thread; start_feed_thread()
"""

import os
import sqlite3
import threading
import time
import logging

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("pinnacle_feed")

POLL_INTERVAL = 120  # seconds between fetches

_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
}

_COMPLETED_DB = os.path.join(
    os.path.dirname(__file__), "..", "data", "deepfield_browser_data", "completed_fixtures.db"
)

_STOP = threading.Event()


# ─── Pinnacle API helpers ──────────────────────────────────────────────────────

def _get(path, params=None, timeout=15):
    if requests is None:
        raise RuntimeError("requests not installed")
    r = requests.get(f"{_BASE}{path}", params=params, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _amer_to_dec(amer):
    """Convert American odds to decimal."""
    if amer is None:
        return None
    if amer > 0:
        return round(amer / 100.0 + 1.0, 4)
    if amer < 0:
        return round(100.0 / abs(amer) + 1.0, 4)
    return None


def _devig(h, d, a):
    """Simple proportional de-vig → (p_home, p_draw, p_away)."""
    vals = [x for x in [h, d, a] if x and x > 1.0]
    inv = sum(1.0 / x for x in vals)
    if not inv:
        return None, None, None
    p_h = round((1.0 / h) / inv, 6) if h else None
    p_d = round((1.0 / d) / inv, 6) if d else None
    p_a = round((1.0 / a) / inv, 6) if a else None
    return p_h, p_d, p_a


# ─── Core fetch ───────────────────────────────────────────────────────────────

def fetch_1x2_snapshot():
    """
    Fetch current Pinnacle 1X2 odds for all upcoming soccer matches.
    Returns list of dicts with keys:
      match_key, home_team, away_team, league,
      h_dec, d_dec, a_dec, p_home, p_draw, p_away, starts_ts
    """
    matchups = _get("/sports/29/matchups", params={"withSpecials": "true", "brandId": "0"})
    markets  = _get("/sports/29/markets/straight")

    # Index markets by matchupId — keep only moneyline period=0
    mk_idx = {}
    for m in markets:
        if m.get("type") == "moneyline" and m.get("period") == 0:
            mk_idx.setdefault(m["matchupId"], []).append(m)

    results = []
    now_ts = time.time()

    for item in matchups:
        if item.get("type") != "matchup":
            continue
        parts = item.get("participants", [])
        home_p = next((p for p in parts if p.get("alignment") == "home"), None)
        away_p = next((p for p in parts if p.get("alignment") == "away"), None)
        if not home_p or not away_p:
            continue

        ml_list = mk_idx.get(item["id"], [])
        if not ml_list:
            continue
        m = ml_list[0]

        prices = {pr["designation"]: pr["price"] for pr in m.get("prices", []) if "designation" in pr}
        if "home" not in prices or "away" not in prices:
            continue

        h_dec = _amer_to_dec(prices.get("home"))
        d_dec = _amer_to_dec(prices.get("draw"))
        a_dec = _amer_to_dec(prices.get("away"))

        if not h_dec or not a_dec:
            continue

        p_h, p_d, p_a = _devig(h_dec, d_dec, a_dec)
        if p_h is None or p_a is None:
            continue

        # Parse kickoff
        start_str = item.get("startTime", "")
        starts_ts = None
        if start_str:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                starts_ts = dt.timestamp()
            except Exception:
                pass

        # Skip matches that already kicked off
        if starts_ts and starts_ts < now_ts - 120:
            continue

        home_name = home_p.get("name", "")
        away_name = away_p.get("name", "")
        league = item.get("league", {}).get("name", "")

        results.append({
            "match_key": f"{home_name} vs {away_name}",
            "home_team": home_name,
            "away_team": away_name,
            "league": league,
            "h_dec": h_dec,
            "d_dec": d_dec,
            "a_dec": a_dec,
            "p_home": p_h,
            "p_draw": p_d,
            "p_away": p_a,
            "starts_ts": starts_ts,
        })

    return results


# ─── DB writer ────────────────────────────────────────────────────────────────

def _ensure_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sharp_odds_history (
            match_key TEXT, home_team TEXT, away_team TEXT, league TEXT,
            selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_soh_ts ON sharp_odds_history(ts)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_soh_teams ON sharp_odds_history(home_team, away_team, selection)"
    )
    conn.commit()


def write_snapshot(snapshot):
    """Write a list of fetch_1x2_snapshot() results to sharp_odds_history."""
    if not snapshot:
        return 0

    if not os.path.exists(os.path.dirname(_COMPLETED_DB)):
        return 0

    ts = time.time()
    rows = []
    for item in snapshot:
        mk = item["match_key"]
        h, a = item["home_team"], item["away_team"]
        lg = item["league"]
        sts = item.get("starts_ts")

        for sel, dec, prob in [
            ("home", item["h_dec"], item["p_home"]),
            ("draw", item["d_dec"], item["p_draw"]),
            ("away", item["a_dec"], item["p_away"]),
        ]:
            if dec is None or prob is None:
                continue
            rows.append((mk, h, a, lg, sel, dec, prob, ts, sts))

    if not rows:
        return 0

    conn = sqlite3.connect(_COMPLETED_DB, timeout=10)
    try:
        _ensure_table(conn)
        conn.executemany(
            "INSERT INTO sharp_odds_history "
            "(match_key, home_team, away_team, league, selection, decimal_odds, devig_prob, ts, starts_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        return len(rows) // 3  # matches, not price rows
    finally:
        conn.close()


# ─── Public function for odds_aggregator / pinnacle_value ────────────────────

def fetch_pinnacle_1x2():
    """
    Return current Pinnacle 1X2 data as a dict keyed by
    'Home vs Away' → {'home': dec_odds, 'draw': dec_odds, 'away': dec_odds,
                       'p_home': float, 'p_draw': float, 'p_away': float}.
    Drops after-kickoff matches. Never raises (returns {} on error).
    """
    try:
        snap = fetch_1x2_snapshot()
        return {
            item["match_key"]: {
                "home": item["h_dec"],
                "draw": item.get("d_dec"),
                "away": item["a_dec"],
                "p_home": item["p_home"],
                "p_draw": item.get("p_draw"),
                "p_away": item["p_away"],
                "league": item["league"],
            }
            for item in snap
        }
    except Exception as e:
        logger.debug("fetch_pinnacle_1x2 error: %s", e)
        return {}


# ─── Background thread ────────────────────────────────────────────────────────

def _feed_loop():
    logger.info("[PinFeed] Starting Pinnacle odds feed (interval=%ds)", POLL_INTERVAL)
    consecutive_errors = 0
    while not _STOP.is_set():
        try:
            snap = fetch_1x2_snapshot()
            n = write_snapshot(snap)
            # Also persist O/U 2.5 prices so CLV can be computed at settlement
            try:
                totals = fetch_pinnacle_totals(line=2.5)
                n_ou = write_ou25_snapshot(totals)
                logger.info("[PinFeed] Wrote %d matches 1X2 + %d matches OU25", n, n_ou)
            except Exception as _ou_err:
                logger.warning("[PinFeed] OU25 snapshot error (non-fatal): %s", _ou_err)
                logger.info("[PinFeed] Wrote %d matches (%d prices)", n, n * 3)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            backoff = min(30 * consecutive_errors, 300)
            logger.warning("[PinFeed] Error (attempt %d): %s — retrying in %ds", consecutive_errors, e, backoff)
            _STOP.wait(backoff)
            continue
        _STOP.wait(POLL_INTERVAL)
    logger.info("[PinFeed] Feed stopped.")


def start_feed_thread(daemon=True):
    """Launch the Pinnacle feed as a background thread. Idempotent — safe to call multiple times."""
    t = threading.Thread(target=_feed_loop, name="pinnacle-feed", daemon=daemon)
    t.start()
    return t


def stop_feed():
    _STOP.set()


# ─── Compatibility shims for old sharp_scraper imports ───────────────────────

SOCCER = 29  # Pinnacle sport ID for soccer


def fetch_pinnacle_totals(line=2.5):
    """Return dict of 'Home vs Away' -> {'over': dec, 'under': dec, 'p_over': float, 'p_under': float, 'starts_ts': float|None}."""
    try:
        matchups = _get("/sports/29/matchups", params={"withSpecials": "true", "brandId": "0"})
        markets = _get("/sports/29/markets/straight")
        mk_idx = {}
        for m in markets:
            if m.get("type") == "total" and m.get("period") == 0:
                mk_idx.setdefault(m["matchupId"], []).append(m)
        now_ts = time.time()
        result = {}
        for item in matchups:
            if item.get("type") != "matchup":
                continue
            parts = item.get("participants", [])
            home_p = next((p for p in parts if p.get("alignment") == "home"), None)
            away_p = next((p for p in parts if p.get("alignment") == "away"), None)
            if not home_p or not away_p:
                continue
            starts_ts = None
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(item.get("startTime", "").replace("Z", "+00:00"))
                starts_ts = dt.timestamp()
            except Exception:
                pass
            if starts_ts and starts_ts < now_ts - 120:
                continue
            for m in mk_idx.get(item["id"], []):
                if abs((m.get("key") or "").count(str(line))) == 0:
                    continue
                prices = {pr["designation"]: pr["price"] for pr in m.get("prices", []) if "designation" in pr}
                if "over" not in prices or "under" not in prices:
                    continue
                o_dec = _amer_to_dec(prices["over"])
                u_dec = _amer_to_dec(prices["under"])
                if not o_dec or not u_dec:
                    continue
                inv = 1 / o_dec + 1 / u_dec
                result[f"{home_p['name']} vs {away_p['name']}"] = {
                    "over": o_dec, "under": u_dec,
                    "p_over": round((1 / o_dec) / inv, 4),
                    "p_under": round((1 / u_dec) / inv, 4),
                    "starts_ts": starts_ts,
                    "_home": home_p["name"],
                    "_away": away_p["name"],
                }
                break
        return result
    except Exception as e:
        logger.debug("fetch_pinnacle_totals error: %s", e)
        return {}


def write_ou25_snapshot(totals: dict) -> int:
    """Write O/U 2.5 Pinnacle prices to sharp_odds_history for CLV tracking.

    Selection values are stored as 'over_2.5' and 'under_2.5' so they are
    distinct from the 1X2 rows ('home', 'draw', 'away') and can be looked up
    at settlement time by clv_from_pinnacle_ou25().

    Returns the number of matches written (0 on error or empty input).
    """
    if not totals:
        return 0
    if not os.path.exists(os.path.dirname(_COMPLETED_DB)):
        return 0

    ts = time.time()
    rows = []
    for match_key, data in totals.items():
        h = data.get("_home") or match_key.split(" vs ")[0]
        a = data.get("_away") or (match_key.split(" vs ")[1] if " vs " in match_key else "")
        sts = data.get("starts_ts")
        o_dec = data.get("over")
        u_dec = data.get("under")
        p_over = data.get("p_over")
        p_under = data.get("p_under")
        if o_dec and p_over:
            rows.append((match_key, h, a, "", "over_2.5", o_dec, p_over, ts, sts))
        if u_dec and p_under:
            rows.append((match_key, h, a, "", "under_2.5", u_dec, p_under, ts, sts))

    if not rows:
        return 0

    conn = sqlite3.connect(_COMPLETED_DB, timeout=10)
    try:
        _ensure_table(conn)
        conn.executemany(
            "INSERT INTO sharp_odds_history "
            "(match_key, home_team, away_team, league, selection, decimal_odds, devig_prob, ts, starts_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        return len(rows) // 2
    finally:
        conn.close()


# ─── Standalone ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print("Fetching Pinnacle 1X2 snapshot...")
    snap = fetch_1x2_snapshot()
    n = write_snapshot(snap)
    print(f"Written: {n} matches, {n*3} price rows")
    for item in snap[:5]:
        d_str = f"{item['d_dec']}({item['p_draw']:.1%})" if item.get("p_draw") else "-"
        print(
            f"  {item['home_team']} vs {item['away_team']} | {item['league']}"
            f" | h={item['h_dec']}({item['p_home']:.1%}) d={d_str} a={item['a_dec']}({item['p_away']:.1%})"
        )
