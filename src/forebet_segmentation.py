"""
forebet_segmentation.py — Phase 6 (Forebet Analysis) for DeepFieldPro.

Segments SETTLED bets from data/bet_log.db into Forebet-confirmed /
non-confirmed / arbitrage / high-edge / low-edge / high-confidence /
low-confidence buckets and reports ROI, win rate, bootstrap 95% CI, and
expected (Kelly) growth per segment.

Data source note: bet_log.db's `bet_source` column distinguishes strategies.
'TIPSTER_FOREBET' = Forebet-confirmed picks; 'AI' = the base model's own
picks (used here as the "non-confirmed" comparison group, since it is the
same underlying model without Forebet agreement). There is currently no
Arena-arbitrage bet_source in bet_log.db (arbitrage is an Arena-only,
real-money concept tracked separately in data/arena_ledger.db, which has
zero settled bets so far — see attribution_engine.py) — the arbitrage
segment therefore reports n=0 honestly rather than being silently omitted.

VOID results (bet cancelled/no market outcome — edge_pct is always 0 for
these in the current data) are excluded from every segment's win-rate/ROI
denominator, matching standard settlement-accounting practice: a void bet
neither won nor lost and returns the stake, so including it would understate
true ROI on the bets that actually resolved.
"""

import os
import sqlite3

from src.edge_threshold_analysis import bootstrap_roi_ci, kelly_growth_rate

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def _load_settled_bets(db_path=None, bet_source=None, market_type=None):
    """
    Rows with result in ('W','L') only (VOID excluded — see module
    docstring). Returns list of dicts: stake, pnl, edge_pct, fair_odds, won.

    `market_type` optionally restricts to a single market (e.g. "1X2") —
    important because bet_log.db's TIPSTER_FOREBET rows mix 1X2 and
    Over/Under 2.5 bets, but Arena's live Forebet-confirmation gate
    (src/arena_betting.py's _tipster_agrees()) only ever matches 1X2
    predictions. Mixing markets would confound any segment comparison meant
    to inform that gate.
    """
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT stake, pnl, edge_pct, fair_odds, result FROM bet_log WHERE result IN ('W','L')"
    params = []
    if bet_source:
        query += " AND bet_source = ?"
        params.append(bet_source)
    if market_type:
        query += " AND market_type = ?"
        params.append(market_type)
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    out = []
    for r in rows:
        stake = r["stake"]
        if not stake:
            continue
        out.append(
            {
                "stake": float(stake),
                "pnl": float(r["pnl"] or 0.0),
                "edge_pct": float(r["edge_pct"] or 0.0),
                "fair_odds": float(r["fair_odds"]) if r["fair_odds"] else None,
                "won": r["result"] == "W",
            }
        )
    return out


def _segment_stats(bets, kelly_fraction=0.25):
    """ROI, win rate, bootstrap 95% CI, and Kelly growth for one bet list."""
    n = len(bets)
    if n == 0:
        return {
            "n": 0, "roi": None, "win_rate": None, "roi_ci_95": None,
            "expected_growth": None, "total_staked": 0.0, "total_pnl": 0.0,
        }
    total_staked = sum(b["stake"] for b in bets)
    total_pnl = sum(b["pnl"] for b in bets)
    returns = [b["pnl"] / b["stake"] for b in bets if b["stake"]]
    wins = sum(1 for b in bets if b["won"])
    return {
        "n": n,
        "roi": round(total_pnl / total_staked, 4) if total_staked else None,
        "win_rate": round(wins / n, 4),
        "roi_ci_95": bootstrap_roi_ci(returns),
        "expected_growth": round(kelly_growth_rate(returns, kelly_fraction), 6)
        if kelly_growth_rate(returns, kelly_fraction) is not None else None,
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
    }


def build_forebet_segmentation_report(
    db_path=None, edge_threshold_pct=5.0, confidence_threshold=0.50, market_type="1X2"
):
    """
    Full Phase 6 report: forebet_confirmed / non_confirmed / arbitrage
    (structural, currently always n=0 — see module docstring) segments, plus
    high/low edge and high/low confidence cuts WITHIN the forebet_confirmed
    group (the strategy this project has already validated as its only
    CI-above-zero paper strategy — see CLAUDE.md's Forebet Confirm Gate
    note), so the edge/confidence cuts answer "where within Forebet-agreement
    is the edge concentrated," not a repeat of the confirmed-vs-not split.

    Defaults to market_type="1X2" (not all markets) because Arena's live
    Forebet gate only ever consults 1X2 predictions — see _load_settled_bets.
    Pass market_type=None to include every market (useful for a broader,
    all-strategies view, but not directly comparable to what gates Arena).
    """
    forebet_bets = _load_settled_bets(db_path, bet_source="TIPSTER_FOREBET", market_type=market_type)
    ai_bets = _load_settled_bets(db_path, bet_source="AI", market_type=market_type)

    high_edge = [b for b in forebet_bets if b["edge_pct"] >= edge_threshold_pct]
    low_edge = [b for b in forebet_bets if b["edge_pct"] < edge_threshold_pct]

    def _implied_prob(b):
        return (1.0 / b["fair_odds"]) if b["fair_odds"] else None

    high_conf = [b for b in forebet_bets if _implied_prob(b) is not None and _implied_prob(b) >= confidence_threshold]
    low_conf = [b for b in forebet_bets if _implied_prob(b) is not None and _implied_prob(b) < confidence_threshold]

    return {
        "forebet_confirmed": _segment_stats(forebet_bets),
        "non_confirmed": _segment_stats(ai_bets),
        "arbitrage": _segment_stats([]),  # see module docstring — no data source yet
        "forebet_high_edge": _segment_stats(high_edge),
        "forebet_low_edge": _segment_stats(low_edge),
        "forebet_high_confidence": _segment_stats(high_conf),
        "forebet_low_confidence": _segment_stats(low_conf),
        "thresholds": {
            "edge_threshold_pct": edge_threshold_pct,
            "confidence_threshold": confidence_threshold,
            "market_type": market_type,
        },
    }
