"""
sharp_edge.py - turn Pinnacle (sharp) odds into a tradable signal for Betarabia.
===============================================================================
Implements the two edges your backtests validated, on the book you bet (Betarabia):

  1. SHARP STEAM  - the de-vigged Pinnacle probability for a side moving up over
     time. Betting the side the sharp money moved toward was the strongest signal
     in tools/backtest_market_signals.py (+20.9% ROI at >=5% moves).
  2. LAGGING VALUE - Betarabia still offering a BETTER price than Pinnacle's
     current line. The only durable edge found was taking a better-than-close
     number; on a single book that means catching it before it corrects.

A bet qualifies only when BOTH hold for the same side: the sharp line steamed
toward it AND Betarabia's price is still better than the sharp price.

This module only READS Pinnacle and LOGS history. It places nothing.
"""

import os
import time
import sqlite3
import threading
import datetime
from difflib import SequenceMatcher

from src.sharp_scraper import fetch_pinnacle_1x2

_DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "deepfield_browser_data",
    "completed_fixtures.db",
)
SNAP_INTERVAL = 120  # seconds between sharp snapshots
# Cross-book matching is the #1 risk: a wrong match bets the wrong game. So we
# require BOTH teams to be a STRONG name match AND (when known) the kickoffs to
# line up. Strict by design — a missed match is far cheaper than a false one.
MATCH_MIN = 0.82  # per-team name-similarity floor
MATCH_MARGIN = 0.15  # best match must beat 2nd-best by this (reject ambiguous)
KICKOFF_WINDOW = 900  # seconds; kickoffs must agree within 15 min if both known
# A Betarabia price more than this much +EV vs the sharp FAIR prob is not real value -
# it's a stale/garbled odds_stream price. Treat it as suspect, not "lagging value", so
# neither sharp strategy bets it. (Belgium @3.7 as a 60% favourite = +122% EV = stale.)
TRAP_EV_CAP = 0.20
_started = False
# bet_log side strings -> sharp designation
_SIDE = {"Home": "home", "Draw": "draw", "Away": "away"}


def _devig(odds):
    inv = {k: 1.0 / v for k, v in odds.items() if v and v > 0}
    tot = sum(inv.values())
    if tot <= 0 or len(inv) < 2:
        return None
    return {k: v / tot for k, v in inv.items()}


def _sim(a, b):
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _parse_ts(iso):
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _init_db():
    con = sqlite3.connect(_DB)
    con.execute(
        """CREATE TABLE IF NOT EXISTS sharp_odds_history (
            match_key TEXT, home_team TEXT, away_team TEXT, league TEXT,
            selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL,
            starts_ts REAL)"""
    )
    # Migrate an older table that predates starts_ts.
    cols = [r[1] for r in con.execute("PRAGMA table_info(sharp_odds_history)")]
    if "starts_ts" not in cols:
        con.execute("ALTER TABLE sharp_odds_history ADD COLUMN starts_ts REAL")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_sharp_key ON sharp_odds_history(match_key)"
    )
    con.commit()
    con.close()


def record_sharp_snapshot():
    """Fetch Pinnacle 1X2, de-vig, and append one snapshot per selection. Returns
    (rows_written, fixtures_seen)."""
    _init_db()
    data = fetch_pinnacle_1x2()
    now = time.time()
    con = sqlite3.connect(_DB)
    cur = con.cursor()
    n = 0
    for key, v in data.items():
        odds = {s: v.get(s) for s in ("home", "draw", "away") if v.get(s)}
        dv = _devig(odds)
        if not dv:
            continue
        starts = _parse_ts(v.get("starts"))
        for sel, o in odds.items():
            cur.execute(
                "INSERT INTO sharp_odds_history VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    v["home_team"],
                    v["away_team"],
                    v.get("league"),
                    sel,
                    o,
                    dv.get(sel),
                    now,
                    starts,
                ),
            )
            n += 1
    # Bound growth: steam only needs same-day pre-kickoff history, so drop snapshots
    # older than 3 days (otherwise this table grows ~159 fixtures x 3 sels every 120s).
    try:
        con.execute("DELETE FROM sharp_odds_history WHERE ts < ?", (now - 3 * 86400,))
        con.commit()
    except Exception:
        pass
    con.close()
    return n, len(data)


# --- In-memory caches (the gate calls these ~150x/sweep; querying + fuzzy-matching
#     SQLite per call hogged the GIL and starved the dashboard). Refreshed on a TTL. ---
_CACHE_TTL = 90
_fix_cache = {"ts": 0.0, "rows": []}  # [(match_key, home, away, starts_ts)]
_series_cache = {}  # match_key -> ((e, lp, lo, nts), ts)
_match_memo = {}  # (home_lc, away_lc, ko_bucket) -> match_key|None


def _fixtures():
    now = time.time()
    if _fix_cache["rows"] and (now - _fix_cache["ts"]) < _CACHE_TTL:
        return _fix_cache["rows"]
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT match_key, home_team, away_team, MAX(starts_ts) "
            "FROM sharp_odds_history GROUP BY match_key"
        ).fetchall()
        con.close()
    except sqlite3.OperationalError:
        rows = []
    _fix_cache["rows"], _fix_cache["ts"] = rows, now
    _match_memo.clear()  # fixture set changed -> drop memoized matches
    return rows


def _match_key(home, away, kickoff_ts=None):
    """Strictly match a Betarabia (home, away[, kickoff]) to a Pinnacle match_key.
    Requires both team names >= MATCH_MIN, an unambiguous best match, and (when
    both kickoffs are known) kickoffs within KICKOFF_WINDOW. Returns None if unsure.
    Memoized per fixture so the 3 selections of a match don't re-match."""
    ko_bucket = int(kickoff_ts // 600) if kickoff_ts else 0
    memo_key = ((home or "").lower(), (away or "").lower(), ko_bucket)
    if memo_key in _match_memo:
        return _match_memo[memo_key]
    rows = _fixtures()
    scored = []
    for key, h, a, starts in rows:
        sh, sa = _sim(home, h), _sim(away, a)
        if sh < MATCH_MIN or sa < MATCH_MIN:
            continue
        # Kickoff sanity check — the strongest disambiguator across books.
        if kickoff_ts and starts and abs(kickoff_ts - starts) > KICKOFF_WINDOW:
            continue
        scored.append((sh + sa, key))
    result = None
    if scored:
        scored.sort(reverse=True)
        # Reject ambiguous (two plausible fixtures) — never risk the wrong one.
        if not (len(scored) > 1 and (scored[0][0] - scored[1][0]) < MATCH_MARGIN):
            result = scored[0][1]
    _match_memo[memo_key] = result
    return result


def _series(match_key):
    """Per-selection (earliest_prob, latest_prob, latest_decimal, n_ts) for a match_key.
    Cached per key on a TTL — only the few matched fixtures ever hit the DB, and the 3
    selections x 2 strategies of a match reuse one query instead of six."""
    now = time.time()
    cached = _series_cache.get(match_key)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT selection, devig_prob, decimal_odds, ts FROM sharp_odds_history "
            "WHERE match_key=? ORDER BY ts ASC",
            (match_key,),
        ).fetchall()
        con.close()
    except sqlite3.OperationalError:
        rows = []
    earliest, latest_p, latest_o = {}, {}, {}
    times = set()
    for sel, p, o, ts in rows:
        times.add(ts)
        earliest.setdefault(sel, p)
        latest_p[sel] = p
        latest_o[sel] = o
    result = (earliest, latest_p, latest_o, len(times))
    _series_cache[match_key] = (result, now)
    return result


def evaluate(home, away, side, bet_odds, kickoff_ts=None):
    """Return the sharp signal for one Betarabia 1X2 pick.

    side: 'Home'|'Draw'|'Away' (the bet_log side prefix). bet_odds: Betarabia decimal.
    kickoff_ts: Betarabia kickoff epoch (used to disambiguate the cross-book match).
    Returns dict with sharp_move (de-vigged prob move toward the side, in %),
    sharp_odds (Pinnacle decimal for the side), lagging (Betarabia price > sharp),
    matched (bool), snapshots (count), and qualifies (move>=min AND lagging)."""
    sel = _SIDE.get(side.split(" (")[0] if side else "", None)
    out = {
        "matched": False,
        "snapshots": 0,
        "sharp_move": 0.0,
        "sharp_odds": None,
        "lagging": False,
        "qualifies": False,
    }
    if sel is None:
        return out
    key = _match_key(home, away, kickoff_ts)
    if not key:
        return out
    earliest, latest_p, latest_o, nts = _series(key)
    out["matched"] = True
    out["snapshots"] = nts
    out["sharp_odds"] = latest_o.get(sel)
    if sel in latest_p and sel in earliest:
        out["sharp_move"] = round((latest_p[sel] - earliest[sel]) * 100.0, 2)
    if out["sharp_odds"] and bet_odds:
        # Lagging value = Betarabia pays MORE than sharp, but not IMPLAUSIBLY more
        # (a huge gap vs the sharp fair prob means the Betarabia price is stale/garbled).
        fair = latest_p.get(sel)
        ev_fair = (fair * bet_odds - 1.0) if fair else None
        out["ev_fair"] = round(ev_fair, 4) if ev_fair is not None else None
        out["lagging"] = bool(
            bet_odds > out["sharp_odds"]
            and ev_fair is not None
            and ev_fair <= TRAP_EV_CAP
        )
    return out


def qualifies(home, away, side, bet_odds, min_move_pct, kickoff_ts=None):
    """True iff sharp steam toward `side` >= min_move_pct AND Betarabia lags the sharp price."""
    s = evaluate(home, away, side, bet_odds, kickoff_ts)
    s["qualifies"] = bool(
        s["matched"]
        and s["snapshots"] >= 2
        and s["sharp_move"] >= min_move_pct
        and s["lagging"]
    )
    return s


def value_signal(home, away, side, bet_odds, kickoff_ts=None):
    """Pure value vs the SHARP fair line. Pinnacle's de-vigged probability is the best
    estimate of the true chance; if Betarabia's odds pay MORE than that fair price, the
    bet is +EV by construction:  ev = sharp_fair_prob * betarabia_odds - 1.
    Fires on the first snapshot (no move needed), so it catches mispricing far more often
    than steam. Returns sharp_fair_prob, ev, matched."""
    sel = _SIDE.get(side.split(" (")[0] if side else "", None)
    out = {"matched": False, "sharp_fair_prob": None, "ev": None}
    if sel is None or not bet_odds:
        return out
    key = _match_key(home, away, kickoff_ts)
    if not key:
        return out
    _e, latest_p, _o, _n = _series(key)
    fair = latest_p.get(sel)
    out["matched"] = True
    if fair is None or fair <= 0:
        return out
    out["sharp_fair_prob"] = round(fair, 4)
    out["ev"] = round(fair * bet_odds - 1.0, 4)
    return out


def qualifies_value(home, away, side, bet_odds, min_ev, max_ev, kickoff_ts=None):
    """True iff Betarabia is +EV vs the sharp fair line, within a capped band.
    The cap matters: the backtest showed chasing BIG 'value' selects losing longshots
    (stale/trap odds), so only modest mispricings qualify."""
    s = value_signal(home, away, side, bet_odds, kickoff_ts)
    s["qualifies"] = bool(
        s["matched"] and s["ev"] is not None and min_ev <= s["ev"] <= max_ev
    )
    return s


def _loop():
    while True:
        try:
            n, fx = record_sharp_snapshot()
            print(f"[SHARP] Pinnacle snapshot: {fx} fixtures, {n} selections logged.")
        except Exception as e:
            print(f"[SHARP] snapshot error: {e}")
        time.sleep(SNAP_INTERVAL)


def start_sharp_snapshots():
    """Launch the sharp-odds snapshot thread once (idempotent)."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="sharp-snapshots").start()
    print(f"[*] Sharp (Pinnacle) snapshot thread started (every {SNAP_INTERVAL}s).")


if __name__ == "__main__":
    n, fx = record_sharp_snapshot()
    print(f"snapshot: {fx} fixtures, {n} rows logged")
