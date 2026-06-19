"""
totals_value_report.py — can we make money on Total Goals (O/U 2.5)? (the CHECK)
==============================================================================
Don't model totals (the project's model-on-totals lost). Instead: Pinnacle's de-vigged
O/U probability is the sharp FAIR line — the best free predictor. If Betarabia (a soft book)
pays MORE than that fair price, betting it is +EV by construction (value = sharp lags soft).
This measures, for tonight's fixtures, where Betarabia's O/U 2.5 is +EV vs Pinnacle — the
honest go/no-go before wiring totals into the bet path. Read-only; no live change.
    ev_over  = pinnacle_over_prob  * betarabia_over_odds  - 1
    ev_under = pinnacle_under_prob * betarabia_under_odds - 1
A real edge = consistent modest +EV (cap big "values" as stale, same as 1X2 SHARPV).
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from src.sharp_scraper import fetch_pinnacle_totals
from src.live_predictions_daemon import find_betarabia_odds

TRAP_EV_CAP = 0.20  # ignore implausibly-big "value" (stale/garbled soft prices)


def main():
    sharp = fetch_pinnacle_totals(2.5)
    print(f"Pinnacle O/U 2.5 fixtures: {len(sharp)}\n")
    rows = []
    for match, s in sharp.items():
        h, a = s["home_team"], s["away_team"]
        try:
            od = find_betarabia_odds(h, a)
        except Exception:
            od = None
        if not od:
            continue
        ou = od.get("Over/Under 2.5") or {}
        bo, bu = ou.get("Over"), ou.get("Under")
        for side, b_odds, p_prob in (
            ("Over", bo, s["over_prob"]),
            ("Under", bu, s["under_prob"]),
        ):
            if not b_odds or b_odds <= 1.0:
                continue
            ev = p_prob * b_odds - 1.0
            if 0.0 < ev <= TRAP_EV_CAP:
                rows.append((ev, match, side, b_odds, p_prob))
    rows.sort(reverse=True)
    print("=" * 72)
    print(" TOTAL GOALS (O/U 2.5) VALUE: Betarabia vs Pinnacle sharp fair line")
    print("=" * 72)
    if not rows:
        print(" No modest +EV totals found on the overlap right now.")
        print(
            " (Either Betarabia totals are efficient, or no fixtures overlapped Pinnacle.)"
        )
        return
    print(f"{'EV':>6}  {'side':5} {'B.odds':>7} {'sharp P':>8}  match")
    print("-" * 72)
    for ev, match, side, b_odds, p_prob in rows[:20]:
        print(f"{ev:>+6.1%}  {side:5} {b_odds:>7.2f} {p_prob:>8.0%}  {match[:40]}")
    print("-" * 72)
    print(
        f" {len(rows)} modest +EV totals (<= {TRAP_EV_CAP:.0%}). If these persist and beat"
    )
    print(" the close (CLV), wiring a totals SHARPV/steam bet path is justified.")


if __name__ == "__main__":
    main()
