"""forebet_probe.py — read-only Forebet signal probe (runbook tool).

Answers, in one shot, the question that matters before every match window:
"does the Forebet-confirmation gate currently see the picks it needs?"

Prints Forebet predictions for today / tomorrow / day+2 (daily pages merged
with the World Cup competition page — see FOREBET_SCRAPER_RELIABILITY.md).

Read-only: fetches public pages only. Places nothing, writes nothing.

Usage:
    .venv\\Scripts\\python.exe tools\\forebet_probe.py
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows consoles often run legacy codepages (cp1256 etc.) that can't print
# accented team names — never let a Unicode print kill a diagnostics run.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.tipster_scraper import get_forebet_predictions  # noqa: E402


def main() -> int:
    today = datetime.date.today()
    days = [(today + datetime.timedelta(days=i)).isoformat() for i in range(3)]

    for d in days:
        preds = get_forebet_predictions(d)
        print(f"\n=== {d}: {len(preds)} Forebet predictions ===")
        for p in preds:
            print(
                f"  {p['home_team']} vs {p['away_team']} -> {p['predicted_side']}"
                f" (H{p['prob_home']}/D{p['prob_draw']}/A{p['prob_away']})"
            )
        if not preds:
            print("  (none — if Forebet visibly shows picks for this date, "
                  "suspect a fetch block or layout change; see runbook)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
