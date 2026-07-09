"""
Phase 4 CLI: calibration report (Brier/LogLoss/ECE/MCE + reliability bins)
over settled Arena real-money bets. READ-ONLY.

Uses the same settled-bet extraction as tools/attribution_report.py
(state["placed"] + state["settlements"]) so the two reports always agree on
"what counts as settled." With few/no settled Arena bets yet (expected early
in a tournament), this correctly reports n=0 rather than fabricating numbers
— see src/calibration_metrics.py's empty-input contract.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json

from src.arena_betting import _load_state
from src.attribution_engine import settlement_map
from src.calibration_metrics import calibration_summary

state = _load_state()
settled = settlement_map(state)

probs, outcomes = [], []
for p in state.get("placed", []) or []:
    if not p.get("ok"):
        continue
    fid = p.get("fixture_id")
    winning_outcome = settled.get(str(fid))
    if winning_outcome is None or p.get("model_prob") is None:
        continue
    probs.append(float(p["model_prob"]))
    outcomes.append(1 if p.get("outcome") == winning_outcome else 0)

summary = calibration_summary(probs, outcomes)
print(json.dumps(summary, indent=2))
