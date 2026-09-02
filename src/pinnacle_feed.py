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

# Seconds between fetches. Was 45s, which polled ~20x faster than the data it
# was reading: the guest endpoint is Cloudflare-cached with max-age=905, so 19
# of every 20 polls re-downloaded a byte-identical ~24MB payload. 240s stays
# comfortably inside the CDN window (so a refreshed copy is picked up promptly),
# stays under HEARTBEAT_SEC so heartbeat rows keep landing for the 60-minute
# staleness gate, and is far inside that gate either way.
POLL_INTERVAL = 240

# ─── sharp_odds_history growth control ───────────────────────────────────────
# The feed used to append every polled price unconditionally. At POLL_INTERVAL=45s
# that is ~1.03M rows/day; the table reached 65M rows / 16.6 GB, which dominated
# both disk and OS page-cache pressure (random B-tree writes across a 16 GB file
# on every insert, times three indexes).
#
# Two controls bound it, both chosen to preserve every existing read contract:
#   * dedup — an UNCHANGED price is not re-appended, but a heartbeat row is still
#     written every HEARTBEAT_SEC. That keeps "latest row" fresh for the daemon's
#     max_odds_staleness_min gate (default 60 min) and keeps the COUNT(*) >= 10
#     reliability gates in check_value()/_pinnacle_fallback_odds() climbing.
#     Genuine line movement is NEVER deduped — that is the CLV/steam signal.
#   * retention — rows older than SHARP_ODDS_RETENTION_DAYS are purged each cycle.
#     Settlement looks back at most 7 days and wc_upcoming injects 7 days ahead,
#     so 14 days spans every reader with margin.
# 5 min: 12x inside the 60-min staleness gate, and a static line still reaches
# the COUNT(*) >= 10 reliability gate in ~50 min of being listed (fixtures are
# normally listed hours-to-days ahead, and any real price move writes a row
# immediately). Still ~7x fewer rows than the raw 45s poll.
HEARTBEAT_SEC = 300
SHARP_ODDS_RETENTION_DAYS = 14

_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    # Public client key embedded in pinnacle.com web app — required since mid-2026
    "x-api-key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
}

_COMPLETED_DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "deepfield_browser_data",
    "completed_fixtures.db",
)

_STOP = threading.Event()


# ─── Pinnacle API helpers ──────────────────────────────────────────────────────


def _get_raw(path, params=None, timeout=15):
    """Issue the request and return the raw Response (headers included)."""
    if requests is None:
        raise RuntimeError("requests not installed")
    # Fresh session per request — avoids Pinnacle blocking persistent connections
    with requests.Session() as s:
        s.headers.update(_HEADERS)
        r = s.get(f"{_BASE}{path}", params=params, timeout=timeout)
    r.raise_for_status()
    return r


def _get(path, params=None, timeout=15):
    return _get_raw(path, params=params, timeout=timeout).json()


# ─── Shared raw-response cache ────────────────────────────────────────────────
# The guest endpoint sits behind Cloudflare and says so:
#     cache-control: public, max-age=905, must-revalidate
#     cf-cache-status: HIT
#     age: 809
# So the data behind it only changes about every 15 minutes. Meanwhile all three
# fetchers (fetch_1x2_snapshot / fetch_pinnacle_totals / fetch_pinnacle_btts)
# request the SAME two paths, and both the feed loop and the prediction daemon
# call them every cycle — six round-trips of a ~24MB payload where two would do,
# repeated far faster than the bytes ever change.
#
# The TTL is taken from the CDN's OWN remaining freshness (max-age minus age)
# rather than a number we invent. That is what makes this safe: the cache can
# never hand back anything staler than what the CDN was already going to serve,
# so it adds exactly zero staleness to the edge calculation — it only stops us
# re-downloading bytes we have already been given.
_MIN_CACHE_SEC = 30.0  # floor, so a nearly-expired CDN copy still dedups a cycle
_MAX_CACHE_SEC = 900.0
_DEFAULT_CACHE_SEC = 120.0  # used when the response carries no cache-control
_RESP_CACHE = {}  # path -> (expires_at, payload)
_CACHE_LOCK = threading.Lock()


def _cache_ttl_from_headers(headers):
    """Seconds this payload stays valid, derived from the CDN's own headers."""
    cc = (headers or {}).get("cache-control") or ""
    max_age = None
    for part in cc.split(","):
        part = part.strip().lower()
        if part.startswith("max-age="):
            try:
                max_age = float(part.split("=", 1)[1])
            except (ValueError, IndexError):
                max_age = None
            break
    if max_age is None:
        return _DEFAULT_CACHE_SEC
    try:
        age = float((headers or {}).get("age") or 0.0)
    except (TypeError, ValueError):
        age = 0.0
    remaining = max_age - age
    # Clamp: never below the floor (so an about-to-expire copy still collapses
    # the duplicate calls inside one cycle) and never above the CDN's own window.
    return max(_MIN_CACHE_SEC, min(remaining, max_age, _MAX_CACHE_SEC))


def _get_cached(path, params=None, timeout=15):
    """_get() for the big shared endpoints, memoised for the CDN's own TTL."""
    now = time.time()
    with _CACHE_LOCK:
        hit = _RESP_CACHE.get(path)
        if hit and hit[0] > now:
            return hit[1]
    # Fetch outside the lock so a slow request never blocks the other thread.
    r = _get_raw(path, params=params, timeout=timeout)
    payload = r.json()
    ttl = _cache_ttl_from_headers(getattr(r, "headers", {}))
    with _CACHE_LOCK:
        _RESP_CACHE[path] = (time.time() + ttl, payload)
    return payload


def _cache_clear():
    with _CACHE_LOCK:
        _RESP_CACHE.clear()


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
    matchups = _get_cached(
        "/sports/29/matchups", params={"withSpecials": "true", "brandId": "0"}
    )
    markets = _get_cached("/sports/29/markets/straight")

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

        prices = {
            pr["designation"]: pr["price"]
            for pr in m.get("prices", [])
            if "designation" in pr
        }
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

        results.append(
            {
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
            }
        )

    return results


# ─── DB writer ────────────────────────────────────────────────────────────────


def _ensure_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sharp_odds_history (
            match_key TEXT, home_team TEXT, away_team TEXT, league TEXT,
            selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_soh_ts ON sharp_odds_history(ts)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_soh_teams ON sharp_odds_history(home_team, away_team, selection)"
    )
    # Expression index so LOWER(REPLACE(REPLACE(home_team,...))) lookups in check_value() use the index
    # instead of doing a full table scan (4.3M rows → 2600× speedup per query).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_soh_norm ON sharp_odds_history("
        "LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' ')),"
        "LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' ')),"
        "selection)"
    )
    conn.commit()


def _latest_prices(conn, since_ts):
    """{(match_key, selection): decimal_odds} for rows newer than *since_ts*.

    Bounded by ts so the scan rides idx_soh_ts and only touches the last
    HEARTBEAT_SEC of rows, never the whole table.
    """
    try:
        rows = conn.execute(
            "SELECT match_key, selection, decimal_odds FROM ("
            "  SELECT match_key, selection, decimal_odds,"
            "         ROW_NUMBER() OVER ("
            "             PARTITION BY match_key, selection ORDER BY ts DESC"
            "         ) AS rn"
            "  FROM sharp_odds_history WHERE ts >= ?"
            ") WHERE rn = 1",
            (since_ts,),
        ).fetchall()
    except sqlite3.Error:
        # Window functions need SQLite >= 3.25. Without them we simply do not
        # dedup — correctness first, the retention purge still bounds growth.
        return {}
    return {(r[0], r[1]): r[2] for r in rows}


def _drop_unchanged(conn, rows, ts):
    """Filter *rows* down to prices that moved or whose heartbeat has elapsed.

    rows: (match_key, home, away, league, selection, dec, prob, ts, starts_ts)
    """
    latest = _latest_prices(conn, ts - HEARTBEAT_SEC)
    if not latest:
        return rows
    out = []
    for r in rows:
        prev = latest.get((r[0], r[4]))
        if prev is not None and abs(prev - r[5]) < 1e-9:
            continue  # unchanged and inside the heartbeat window
        out.append(r)
    return out


def purge_sharp_odds_history(days=None):
    """Delete sharp_odds_history rows older than *days*. Returns rows removed.

    Called once per daemon cycle, mirroring _purge_odds_history() for the
    sibling odds_history table (which was already bounded — this one was not).
    Never raises: telemetry retention must not be able to break the loop.
    """
    if days is None:
        days = SHARP_ODDS_RETENTION_DAYS
    if not os.path.exists(_COMPLETED_DB):
        return 0
    try:
        cutoff = time.time() - float(days) * 86400.0
        conn = sqlite3.connect(_COMPLETED_DB, timeout=30)
        try:
            cur = conn.execute(
                "DELETE FROM sharp_odds_history WHERE ts < ?", (cutoff,)
            )
            removed = cur.rowcount or 0
            conn.commit()
            if removed:
                logger.info(
                    "[PinFeed] Purged %d sharp_odds_history rows older than %d days",
                    removed,
                    days,
                )
            return removed
        finally:
            conn.close()
    except Exception as e:
        logger.debug("purge_sharp_odds_history error: %s", e)
        return 0


def write_snapshot(snapshot):
    """Write a list of fetch_1x2_snapshot() results to sharp_odds_history.

    Unchanged prices inside the heartbeat window are skipped (see
    HEARTBEAT_SEC). The return value is still the number of MATCHES in the
    snapshot, not the number of rows actually written, so caller logging keeps
    its original meaning.
    """
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

    n_matches = len(rows) // 3  # matches, not price rows
    conn = sqlite3.connect(_COMPLETED_DB, timeout=10)
    try:
        _ensure_table(conn)
        fresh = _drop_unchanged(conn, rows, ts)
        if fresh:
            conn.executemany(
                "INSERT INTO sharp_odds_history "
                "(match_key, home_team, away_team, league, selection, decimal_odds, devig_prob, ts, starts_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                fresh,
            )
            conn.commit()
        return n_matches
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
            logger.warning(
                "[PinFeed] Error (attempt %d): %s — retrying in %ds",
                consecutive_errors,
                e,
                backoff,
            )
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


def fetch_pinnacle_btts():
    """Return dict of 'Home vs Away' -> {'yes': dec, 'no': dec, 'p_yes': float, 'p_no': float, 'starts_ts': float|None}.

    Both Teams To Score is priced by Pinnacle as a 'special' market (Yes/No
    participants), not a straight market on the parent matchup — its odds live
    in /markets/straight keyed by the SPECIAL's own id, not the parent match id.
    Filtered to the exact full-time description to exclude the 1st-half and
    Total-Goals/Winner combo variants that share the same "Team Props" category.
    """
    try:
        matchups = _get_cached(
            "/sports/29/matchups", params={"withSpecials": "true", "brandId": "0"}
        )
        markets = _get_cached("/sports/29/markets/straight")
        mk_idx = {}
        for m in markets:
            if m.get("type") == "moneyline" and m.get("period") == 0:
                mk_idx.setdefault(m["matchupId"], []).append(m)

        now_ts = time.time()
        result = {}
        for item in matchups:
            if item.get("type") != "special":
                continue
            special = item.get("special") or {}
            if special.get("description") != "Both Teams To Score?":
                continue
            parent = item.get("parent") or {}
            parts = parent.get("participants", [])
            home_p = next((p for p in parts if p.get("alignment") == "home"), None)
            away_p = next((p for p in parts if p.get("alignment") == "away"), None)
            if not home_p or not away_p:
                continue

            starts_ts = None
            try:
                import datetime

                dt = datetime.datetime.fromisoformat(
                    (parent.get("startTime") or "").replace("Z", "+00:00")
                )
                starts_ts = dt.timestamp()
            except Exception:
                pass
            if starts_ts and starts_ts < now_ts - 120:
                continue

            yes_id = next(
                (p["id"] for p in item.get("participants", []) if p.get("name") == "Yes"),
                None,
            )
            no_id = next(
                (p["id"] for p in item.get("participants", []) if p.get("name") == "No"),
                None,
            )
            if yes_id is None or no_id is None:
                continue

            for m in mk_idx.get(item["id"], []):
                prices = {
                    pr.get("participantId"): pr.get("price")
                    for pr in m.get("prices", [])
                }
                if yes_id not in prices or no_id not in prices:
                    continue
                y_dec = _amer_to_dec(prices[yes_id])
                n_dec = _amer_to_dec(prices[no_id])
                if not y_dec or not n_dec:
                    continue
                inv = 1 / y_dec + 1 / n_dec
                result[f"{home_p['name']} vs {away_p['name']}"] = {
                    "yes": y_dec,
                    "no": n_dec,
                    "p_yes": round((1 / y_dec) / inv, 4),
                    "p_no": round((1 / n_dec) / inv, 4),
                    "starts_ts": starts_ts,
                    "_home": home_p["name"],
                    "_away": away_p["name"],
                }
                break
        return result
    except Exception as e:
        logger.debug("fetch_pinnacle_btts error: %s", e)
        return {}


# ─── Compatibility shims for old sharp_scraper imports ───────────────────────

SOCCER = 29  # Pinnacle sport ID for soccer


def fetch_pinnacle_totals(line=2.5):
    """Return dict of 'Home vs Away' -> {'over': dec, 'under': dec, 'p_over': float, 'p_under': float, 'starts_ts': float|None}."""
    try:
        matchups = _get_cached(
            "/sports/29/matchups", params={"withSpecials": "true", "brandId": "0"}
        )
        markets = _get_cached("/sports/29/markets/straight")
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

                dt = datetime.datetime.fromisoformat(
                    item.get("startTime", "").replace("Z", "+00:00")
                )
                starts_ts = dt.timestamp()
            except Exception:
                pass
            if starts_ts and starts_ts < now_ts - 120:
                continue
            for m in mk_idx.get(item["id"], []):
                if abs((m.get("key") or "").count(str(line))) == 0:
                    continue
                prices = {
                    pr["designation"]: pr["price"]
                    for pr in m.get("prices", [])
                    if "designation" in pr
                }
                if "over" not in prices or "under" not in prices:
                    continue
                o_dec = _amer_to_dec(prices["over"])
                u_dec = _amer_to_dec(prices["under"])
                if not o_dec or not u_dec:
                    continue
                inv = 1 / o_dec + 1 / u_dec
                result[f"{home_p['name']} vs {away_p['name']}"] = {
                    "over": o_dec,
                    "under": u_dec,
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
        a = data.get("_away") or (
            match_key.split(" vs ")[1] if " vs " in match_key else ""
        )
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

    n_matches = len(rows) // 2
    conn = sqlite3.connect(_COMPLETED_DB, timeout=10)
    try:
        _ensure_table(conn)
        fresh = _drop_unchanged(conn, rows, ts)
        if fresh:
            conn.executemany(
                "INSERT INTO sharp_odds_history "
                "(match_key, home_team, away_team, league, selection, decimal_odds, devig_prob, ts, starts_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                fresh,
            )
            conn.commit()
        return n_matches
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
