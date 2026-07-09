"""
Phase 6 CLI: Forebet segmentation report against the real data/bet_log.db.
READ-ONLY (only SELECT queries).
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json

from src.forebet_segmentation import build_forebet_segmentation_report

report = build_forebet_segmentation_report()
print(json.dumps(report, indent=2))

if report["forebet_confirmed"]["n"] > 0 and report["forebet_high_edge"]["n"] == 0:
    print(
        "\nNote: TIPSTER_FOREBET rows in bet_log.db all have edge_pct=0 "
        "(this bet source doesn't compute a model-vs-market edge) -- the "
        "high/low-edge split is not meaningful for this segment with the "
        "current data. Reported as-is rather than substituting a different "
        "field silently."
    )
