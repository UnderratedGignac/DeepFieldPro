"""
Phase 7 CLI: CLV report for Arena real-money placed bets, using
src/clv_analysis.py's 30min/1hr/pre-kickoff price-snapshot tracking against
data/polymarket_steam.db. READ-ONLY.

Distinct from the existing tools/clv_report.py, which reports CLV for the
separate PAPER 1X2/bet_log.db strategies (STEAM, TIPSTER_FOREBET, etc.) —
that tool is untouched. This one is Arena-specific (data/arena_autopilot.json
+ data/polymarket_steam.db), reusing the same summarize_clv() aggregation
logic so both reports are comparable in shape.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import datetime as dt

from src.arena_betting import _load_state
from src.clv_analysis import build_clv_report

state = _load_state()

bets = []
for p in state.get("placed", []) or []:
    if not p.get("ok"):
        continue
    kickoff_str = p.get("kickoff", "")
    try:
        kickoff_ts = dt.datetime.strptime(kickoff_str[:16], "%Y-%m-%d %H:%M").timestamp()
    except (ValueError, TypeError):
        kickoff_ts = None
    # signal_ts isn't stored on legacy "placed" entries -- approximate with
    # the entry's own "ts" (when the autopilot cycle recorded it) as a
    # fallback. Going forward, execution_log.db's signal_ts (Phase 2) is the
    # precise source; this CLI reads the Arena state list directly since it's
    # the complete placed-bet history (execution_log only started
    # accumulating once Phase 2 landed).
    try:
        signal_ts = dt.datetime.strptime(p.get("ts", ""), "%Y-%m-%d %H:%M:%S").timestamp()
    except (ValueError, TypeError):
        signal_ts = None
    if signal_ts is None:
        continue
    strategy = "real_arb" if p.get("prob_source") == "ARB" else "tipster_confirmed"
    bets.append(
        {
            "fixture_id": p["fixture_id"],
            "outcome": p["outcome"],
            "signal_ts": signal_ts,
            "kickoff_ts": kickoff_ts,
            "price_taken": p.get("limit_price"),
            "strategy": strategy,
        }
    )

report = build_clv_report(bets)
print(json.dumps(report["summary"], indent=2))
print(f"\n({len(bets)} placed bets checked; {report['summary']['n']} had usable price history for CLV)")
