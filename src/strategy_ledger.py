"""
strategy_ledger.py — per-strategy virtual bankrolls (2026-07-14).

Each strategy (bet_source) gets its own isolated ledger COMPUTED from bet_log
ground truth: starting capital + settled P&L − stakes currently at risk.
Nothing mutates; there are no per-strategy DB files to drift out of sync with
the bet record (the failure mode the physical real/research ledgers showed).
One strategy's results can never touch another's numbers by construction.

Used by the /strategies dashboard pages and ad-hoc reporting.
"""

import datetime
import json
import os
import sqlite3

DEFAULT_STARTING = 100.0
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EPOCH_FILE = os.path.join(_BASE, "data", "strategy_ledger_epoch.json")


def _load_epoch(epoch_file):
    """ISO timestamp of the last ledger reset, or None (count everything)."""
    try:
        with open(epoch_file, encoding="utf-8") as f:
            return (json.load(f) or {}).get("epoch")
    except Exception:
        return None


def reset_strategy_ledgers(when=None, epoch_file=DEFAULT_EPOCH_FILE):
    """Reset every strategy's virtual bankroll to the starting amount by
    stamping a new epoch: only bets placed at/after it count. bet_log history
    is untouched — the ledgers simply restart."""
    epoch = when or datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(epoch_file, "w", encoding="utf-8") as f:
        json.dump({"epoch": epoch}, f)
    return epoch


def strategy_ledgers(db_path, starting=DEFAULT_STARTING, epoch_file=DEFAULT_EPOCH_FILE):
    """{bet_source: ledger dict} for every strategy present in bet_log.

    Ledger fields:
      settled_pnl  — sum of pnl over W/L (VOID contributes 0 by definition)
      open_stake   — money currently at risk in OPEN bets
      balance      — starting + settled_pnl − open_stake  (liquid)
      total_value  — balance + open_stake (what the strategy is worth)
      n_open / n_settled / n_won / n_lost, roi (settled pnl / settled stake)
    """
    epoch = _load_epoch(epoch_file)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT bet_source,
                      COALESCE(SUM(CASE WHEN result IN ('W','L') THEN pnl END), 0),
                      COALESCE(SUM(CASE WHEN result = 'OPEN' THEN stake END), 0),
                      SUM(result = 'OPEN'),
                      SUM(result IN ('W','L')),
                      SUM(result = 'W'),
                      SUM(result = 'L'),
                      COALESCE(SUM(CASE WHEN result IN ('W','L') THEN stake END), 0)
               FROM bet_log
               WHERE bet_source IS NOT NULL AND placed_at >= ?
               GROUP BY bet_source""",
            (epoch or "",),
        ).fetchall()
    finally:
        conn.close()

    out = {}
    for src, pnl, open_stake, n_open, n_settled, n_won, n_lost, settled_stake in rows:
        balance = round(starting + pnl - open_stake, 2)
        out[src] = {
            "settled_pnl": round(pnl, 2),
            "open_stake": round(open_stake, 2),
            "balance": balance,
            "total_value": round(balance + open_stake, 2),
            "n_open": int(n_open or 0),
            "n_settled": int(n_settled or 0),
            "n_won": int(n_won or 0),
            "n_lost": int(n_lost or 0),
            "roi": round(pnl / settled_stake * 100, 1) if settled_stake else 0.0,
            "starting": starting,
        }
    return out


def strategy_bets(db_path, source, limit=200):
    """Recent bets for one strategy, newest first (for the detail page)."""
    conn = sqlite3.connect(db_path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(bet_log)")]
        lg = "league" if "league" in cols else "NULL AS league"
        rows = conn.execute(
            f"""SELECT match_id, market_type, side, entry_odds, stake, result,
                       ROUND(pnl, 2), {lg}, substr(placed_at, 1, 16)
                FROM bet_log WHERE bet_source = ?
                ORDER BY placed_at DESC LIMIT ?""",
            (source, limit),
        ).fetchall()
    finally:
        conn.close()
    keys = ["match", "market", "side", "odds", "stake", "result", "pnl", "league", "placed_at"]
    return [dict(zip(keys, r)) for r in rows]
