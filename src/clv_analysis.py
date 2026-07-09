"""
clv_analysis.py — Phase 7 (Closing Line Value) for DeepFieldPro.

Tracks price snapshots (signal / +30min / +1hr / pre-kickoff = "closing") per
bet from data/polymarket_steam.db's price_history table (already populated
every ~60s by the daemon's record_scan() calls — see
src/polymarket_steam.py), and reports CLV (closing-line value) stats overall
and by strategy.

CLV sign convention (matches tools/backtest_1x2_lines.py and the existing
arena_betting.py clv_records block): clv = price_taken / closing_price - 1.
Positive means we bought cheaper than the market's final pre-kickoff price
implied — the standard "did we get a good number" signal independent of
whether the bet actually won.

Pure computation functions take already-fetched snapshot dicts (testable
without a database); build_clv_report() is the thin DB-querying wrapper used
by tools/clv_report.py.
"""

import os
import sqlite3
import statistics

STEAM_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "polymarket_steam.db")


def _closest_snapshot(conn, fixture_id, outcome, target_ts, max_gap_sec=1800):
    """
    Mid price from price_history closest to target_ts, within max_gap_sec.
    Returns None if no snapshot exists in that window — a data gap, not an
    error (early bets, thin history, etc. are all real, honest possibilities).
    """
    row = conn.execute(
        """
        SELECT mid, recorded_at FROM price_history
        WHERE fixture_id = ? AND outcome = ?
        ORDER BY ABS(recorded_at - ?) ASC LIMIT 1
        """,
        (str(fixture_id), outcome, target_ts),
    ).fetchone()
    if row is None:
        return None
    mid, recorded_at = row
    if abs(recorded_at - target_ts) > max_gap_sec:
        return None
    return mid


def _last_snapshot_before(conn, fixture_id, outcome, kickoff_ts):
    """Last recorded mid strictly before kickoff — this system's definition of 'closing price'."""
    row = conn.execute(
        """
        SELECT mid FROM price_history
        WHERE fixture_id = ? AND outcome = ? AND recorded_at <= ?
        ORDER BY recorded_at DESC LIMIT 1
        """,
        (str(fixture_id), outcome, kickoff_ts),
    ).fetchone()
    return row[0] if row else None


def fetch_price_snapshots(fixture_id, outcome, signal_ts, kickoff_ts, db_path=None):
    """
    {signal_price, price_30min, price_1hr, price_pre_kickoff} for one bet.
    Any field can be None (data gap) — callers must handle that, not assume
    every snapshot exists.
    """
    conn = sqlite3.connect(db_path or STEAM_DB_PATH)
    try:
        return {
            "signal_price": _closest_snapshot(conn, fixture_id, outcome, signal_ts, max_gap_sec=300),
            "price_30min": _closest_snapshot(conn, fixture_id, outcome, signal_ts + 1800),
            "price_1hr": _closest_snapshot(conn, fixture_id, outcome, signal_ts + 3600),
            "price_pre_kickoff": _last_snapshot_before(conn, fixture_id, outcome, kickoff_ts)
            if kickoff_ts
            else None,
        }
    finally:
        conn.close()


def compute_clv(price_taken, closing_price):
    """clv = price_taken / closing_price - 1. None if either price is missing/non-positive."""
    if not price_taken or not closing_price or closing_price <= 0:
        return None
    return round(price_taken / closing_price - 1.0, 6)


def _percentile_positive(values):
    if not values:
        return None
    return round(sum(1 for v in values if v > 0) / len(values), 4)


def summarize_clv(clv_records):
    """
    clv_records: list of {"clv": float or None, "strategy": str or None, ...}.
    Returns overall avg/median/positive% plus a by-strategy breakdown. Only
    records with a non-None clv are counted (missing snapshots are a data
    gap, excluded rather than treated as zero).
    """
    valid = [r for r in clv_records if r.get("clv") is not None]
    if not valid:
        return {
            "n": 0, "avg_clv": None, "median_clv": None,
            "positive_clv_pct": None, "by_strategy": {},
        }
    clvs = [r["clv"] for r in valid]
    by_strategy = {}
    for r in valid:
        by_strategy.setdefault(r.get("strategy") or "unknown", []).append(r["clv"])
    return {
        "n": len(valid),
        "avg_clv": round(statistics.mean(clvs), 6),
        "median_clv": round(statistics.median(clvs), 6),
        "positive_clv_pct": _percentile_positive(clvs),
        "by_strategy": {
            k: {
                "n": len(v),
                "avg_clv": round(statistics.mean(v), 6),
                "positive_clv_pct": _percentile_positive(v),
            }
            for k, v in by_strategy.items()
        },
    }


def build_clv_report(bets, db_path=None):
    """
    `bets`: list of dicts with fixture_id, outcome, signal_ts, kickoff_ts,
    price_taken (the price we actually transacted at, e.g. limit_price), and
    optionally strategy (e.g. "tipster_confirmed" / "real_arb" / "other").

    For each bet, fetches the price-snapshot series and computes CLV against
    the pre-kickoff closing price. Returns per-bet detail plus the
    summarize_clv() aggregate.
    """
    detail = []
    for b in bets:
        snaps = fetch_price_snapshots(
            b["fixture_id"], b["outcome"], b["signal_ts"], b.get("kickoff_ts"), db_path=db_path
        )
        clv = compute_clv(b.get("price_taken"), snaps["price_pre_kickoff"])
        detail.append(
            {
                "fixture_id": b["fixture_id"],
                "outcome": b["outcome"],
                "strategy": b.get("strategy"),
                "price_taken": b.get("price_taken"),
                **snaps,
                "clv": clv,
                "settlement": b.get("settlement"),
            }
        )
    return {"detail": detail, "summary": summarize_clv(detail)}
