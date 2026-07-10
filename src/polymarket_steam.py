"""
Polymarket price history tracker and steam detector for WC 2026 fixtures.

Records Polymarket YES-token mid-prices at each analyze() scan and detects
significant price movements (steam moves) — large, sudden shifts indicate
smart/sharp money repositioning, which is the strongest signal the domestic
backtest validated (+20.9% ROI for ≥5% moves over ≥3% steam threshold).

Key ideas:
  - RISING price on outcome X → market is backing X more strongly → follow
  - FALLING price on outcome X → money rotating out → potential fade signal
  - Market vig < 0 (sum of all mids < 1.0) → mispriced market, higher EV overall
  - De-vigged probability = mid / sum(mids) → cleaner edge measure vs raw mid

Usage (called from arena_betting.analyze()):
    from src.polymarket_steam import record_scan, get_steam_signals, purge_old_records

    record_scan(fixture_id, match_name, all_mid_prices)
    steam = get_steam_signals(fixture_id)  # {outcome: move_pct, ...}
"""

import sqlite3
import time
import threading
import os

_DB_PATH = "data/polymarket_steam.db"
_lock = threading.Lock()


def _conn():
    db = os.path.join(os.path.dirname(os.path.dirname(__file__)), _DB_PATH)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def _init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id TEXT NOT NULL,
                match_name TEXT,
                outcome TEXT NOT NULL,
                mid REAL NOT NULL,
                recorded_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_fid_outcome_ts
            ON price_history (fixture_id, outcome, recorded_at)
        """)
        c.commit()


def record_scan(fixture_id: str, match_name: str, mids: dict):
    """Store current mid prices for a fixture.

    mids = {'home': 0.55, 'draw': 0.20, 'away': 0.25}
    Silently no-ops on any DB error so it never breaks the main bet loop.
    """
    now = time.time()
    with _lock:
        try:
            with _conn() as c:
                for outcome, mid in mids.items():
                    if mid is not None:
                        c.execute(
                            "INSERT INTO price_history "
                            "(fixture_id, match_name, outcome, mid, recorded_at) "
                            "VALUES (?,?,?,?,?)",
                            (str(fixture_id), match_name, outcome, float(mid), now),
                        )
                c.commit()
        except Exception:
            pass


def get_steam_signals(
    fixture_id: str,
    min_move_pct: float = 3.0,
    lookback_seconds: float = 3600 * 4,
) -> dict:
    """Return {outcome: move_pct} for outcomes that moved >= min_move_pct.

    Compares the OLDEST recorded price in the lookback window to the LATEST
    recorded price. Positive = price rose (market backing this outcome).
    Negative = price fell (money rotating out of this outcome).

    Only returns outcomes where |move| >= min_move_pct (default 3%).
    Requires at least 2 data points at different timestamps to fire.
    """
    now = time.time()
    cutoff = now - lookback_seconds
    signals = {}
    try:
        with _conn() as c:
            for outcome in ("home", "draw", "away"):
                rows = c.execute(
                    """
                    SELECT mid, recorded_at FROM price_history
                    WHERE fixture_id = ? AND outcome = ? AND recorded_at >= ?
                    ORDER BY recorded_at ASC
                    """,
                    (str(fixture_id), outcome, cutoff),
                ).fetchall()
                if len(rows) < 2:
                    continue
                old_mid = rows[0]["mid"]
                new_mid = rows[-1]["mid"]
                if old_mid > 0 and rows[0]["recorded_at"] != rows[-1]["recorded_at"]:
                    move_pct = ((new_mid - old_mid) / old_mid) * 100
                    if abs(move_pct) >= min_move_pct:
                        signals[outcome] = round(move_pct, 2)
    except Exception:
        pass
    return signals


def get_price_history(fixture_id: str, outcome: str, limit: int = 50) -> list:
    """Return recent (ts, mid) pairs for a fixture/outcome — newest last."""
    try:
        with _conn() as c:
            rows = c.execute(
                """
                SELECT recorded_at, mid FROM price_history
                WHERE fixture_id = ? AND outcome = ?
                ORDER BY recorded_at DESC LIMIT ?
                """,
                (str(fixture_id), outcome, limit),
            ).fetchall()
            return [(r["recorded_at"], r["mid"]) for r in reversed(rows)]
    except Exception:
        return []


def get_all_steam_signals(min_move_pct: float = 3.0) -> list:
    """Scan ALL tracked fixtures for steam signals. Returns a list of dicts
    suitable for the /arena/api/insights dashboard endpoint."""
    now = time.time()
    cutoff = now - 3600 * 6  # 6-hour lookback for bulk scan
    results = []
    try:
        with _conn() as c:
            # Get distinct fixture_ids with recent data
            fids = c.execute(
                "SELECT DISTINCT fixture_id, match_name FROM price_history "
                "WHERE recorded_at >= ? ORDER BY recorded_at DESC",
                (cutoff,),
            ).fetchall()
            for frow in fids:
                fid = frow["fixture_id"]
                mname = frow["match_name"]
                sigs = get_steam_signals(fid, min_move_pct=min_move_pct)
                if sigs:
                    results.append(
                        {
                            "fixture_id": fid,
                            "match": mname,
                            "steam_signals": sigs,
                            "max_abs_move": max(abs(v) for v in sigs.values()),
                        }
                    )
    except Exception:
        pass
    results.sort(key=lambda r: r["max_abs_move"], reverse=True)
    return results


def purge_old_records(days: int = 5):
    """Delete price history older than N days to keep the DB small."""
    cutoff = time.time() - days * 86400
    try:
        with _conn() as c:
            c.execute("DELETE FROM price_history WHERE recorded_at < ?", (cutoff,))
            c.commit()
    except Exception:
        pass


# Auto-init DB on import
try:
    _init_db()
except Exception:
    pass
