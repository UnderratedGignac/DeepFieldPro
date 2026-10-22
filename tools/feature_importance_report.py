"""
Phase 9 CLI: feature importance over real settled 1X2 bets in bet_log.db.
READ-ONLY.

Feature availability note (verify assumptions, per the master prompt): of
the master prompt's full feature wish-list (Elo prob, Dixon prob, market
prob, edge, confidence, Forebet agreement, spread, liquidity, time-to-
kickoff, tournament stage, odds movement, volatility), bet_log.db's
TIPSTER_FOREBET/AI rows currently carry only: edge_pct, implied confidence
(from fair_odds), and forebet-agreement (bet_source). Liquidity/spread/
time-to-kickoff/tournament-stage/odds-movement ARE now captured going
forward for Arena via execution_log.db (Phase 2) and clv_analysis.py's
price snapshots (Phase 7) -- there just aren't enough SETTLED Arena bets yet
(0, per attribution_engine.py) to fit importances on them. This report uses
what's real and available today; it does not fabricate the missing columns.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import sqlite3

from src.feature_importance import estimate_importance

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")

FEATURE_NAMES = ["edge_pct", "implied_confidence", "forebet_agreement"]


def _load_rows():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT edge_pct, fair_odds, bet_source, result, market_type FROM bet_log "
        "WHERE result IN ('W','L') AND market_type = '1X2' "
        "AND bet_source IN ('TIPSTER_FOREBET', 'AI')"
    ).fetchall()
    conn.close()
    return rows


def main():
    rows = _load_rows()
    X, y = [], []
    for r in rows:
        if not r["fair_odds"]:
            continue
        implied_conf = 1.0 / r["fair_odds"]
        forebet_agreement = 1.0 if r["bet_source"] == "TIPSTER_FOREBET" else 0.0
        X.append([r["edge_pct"] or 0.0, implied_conf, forebet_agreement])
        y.append(1 if r["result"] == "W" else 0)

    print(f"n={len(y)} settled 1X2 bets (TIPSTER_FOREBET + AI) with usable features\n")
    result = estimate_importance(X, y, FEATURE_NAMES)
    print(json.dumps(result, indent=2))

    if all(v is None for v in result.values()):
        print("\nInsufficient data or a single outcome class -- see src/feature_importance.py's contract.")


if __name__ == "__main__":
    main()
