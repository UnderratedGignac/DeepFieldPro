"""
Phase 12 CLI: daily/weekly/monthly report combining every earlier phase's
output — ROI/attribution (Phase 3), CLV (Phase 7), slippage (Phase 2),
calibration (Phase 4), Forebet segmentation (Phase 6), feature importance
(Phase 9), edge-threshold context (Phase 5), and a capital curve (Phase 12).
READ-ONLY.

Usage: .venv\\Scripts\\python.exe tools\\period_report.py [daily|weekly|monthly]
Defaults to "daily".
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import time
import datetime as dt

from src.arena_betting import _load_state
from src.attribution_engine import build_attribution_report, settlement_map
from src.execution_analytics import slippage_report
from src.calibration_metrics import calibration_summary
from src.reporting import filter_by_period, capital_curve


def _placed_bet_ts(p):
    """Parse the Arena state's 'ts' string (%Y-%m-%d %H:%M:%S, UTC) to epoch seconds."""
    try:
        return dt.datetime.strptime(p.get("ts", ""), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=dt.timezone.utc
        ).timestamp()
    except (ValueError, TypeError):
        return None


def build_period_report(period="daily", now_ts=None):
    now_ts = now_ts if now_ts is not None else time.time()
    state = _load_state()
    settled = settlement_map(state)

    all_placed = [p for p in (state.get("placed") or []) if p.get("ok")]
    for p in all_placed:
        p["_ts_epoch"] = _placed_bet_ts(p)
    period_bets = filter_by_period(
        [p for p in all_placed if p.get("_ts_epoch") is not None], "_ts_epoch", period, now_ts
    )

    # Attribution / ROI — reuse Phase 3's report, but scoped to this period's
    # placed bets rather than the whole history (its own state["placed"]/
    # state["settlements"] shape is what build_attribution_report expects).
    period_state = {"placed": period_bets, "settlements": state.get("settlements", [])}
    attribution = build_attribution_report(period_state)

    # Capital curve over the period's SETTLED bets (pnl computed the same
    # way attribution_engine does: binary payout at the actual limit price).
    from src.attribution_engine import binary_payout

    curve_records = []
    for p in period_bets:
        winning_outcome = settled.get(str(p.get("fixture_id")))
        if winning_outcome is None:
            continue
        stake = p.get("staked_usd")
        if stake is None:
            continue
        pnl = binary_payout(float(stake), p.get("limit_price"), p.get("outcome") == winning_outcome)
        curve_records.append({"ts": p["_ts_epoch"], "pnl": pnl})
    curve = capital_curve(curve_records)

    # Calibration over the period's settled bets.
    probs, outcomes = [], []
    for p in period_bets:
        winning_outcome = settled.get(str(p.get("fixture_id")))
        if winning_outcome is None or p.get("model_prob") is None:
            continue
        probs.append(float(p["model_prob"]))
        outcomes.append(1 if p.get("outcome") == winning_outcome else 0)
    calibration = calibration_summary(probs, outcomes)

    # Slippage is drawn from the whole execution_log (Phase 2) rather than
    # period-filtered here — that table doesn't yet carry enough volume to
    # split by period meaningfully; reported as an overall-to-date figure.
    slippage = slippage_report()

    return {
        "period": period,
        "generated_at": dt.datetime.fromtimestamp(now_ts, tz=dt.timezone.utc).isoformat(),
        "n_placed_in_period": len(period_bets),
        "attribution": attribution,
        "capital_curve": curve,
        "calibration": calibration,
        "slippage_to_date": slippage,
    }


def main():
    period = sys.argv[1] if len(sys.argv) > 1 else "daily"
    report = build_period_report(period)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
