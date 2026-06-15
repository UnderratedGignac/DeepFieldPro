"""
softness_report.py — rank tonight's fixtures by Pinnacle's risk limit (softness proxy).
=======================================================================================
Pinnacle's accepted maxRiskStake (already in the free guest /markets/straight payload) is
the best free proxy for "how soft is this market everywhere." LOW limits = Pinnacle itself
is uncertain (early/niche market) -> soft books are most likely mispriced and the cross-book
edge persists longest. Steam / line-shopping capital concentrated on low-limit fixtures
fires fewer -EV bets at higher CLV per bet. This is a MEASURE-FIRST report (no hot-path
change): see where the edge is before gating on it.

Standalone — reuses sharp_scraper's guest API helpers; zero impact on the live feed.
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from src.sharp_scraper import _get, SOCCER  # reuse the keyless guest client


def main():
    matchups = _get(f"/sports/{SOCCER}/matchups")
    straight = _get(f"/sports/{SOCCER}/markets/straight")

    names = {}
    for m in matchups:
        mid = m.get("id")
        parts = m.get("participants") or []
        if mid and len(parts) >= 2:
            home = next((p["name"] for p in parts if p.get("alignment") == "home"), None)
            away = next((p["name"] for p in parts if p.get("alignment") == "away"), None)
            if home and away:
                names[mid] = (f"{home} vs {away}", m.get("league", {}).get("name", ""))

    # max-risk per matchup moneyline (the softness signal)
    rows = []
    for mk in straight:
        if mk.get("type") != "moneyline":
            continue
        mid = mk.get("matchupId")
        if mid not in names:
            continue
        limits = mk.get("limits") or []
        mr = next((l.get("amount") for l in limits if l.get("type") == "maxRiskStake"), None)
        if mr is not None:
            rows.append((mr, names[mid][0], names[mid][1]))

    rows.sort(key=lambda r: r[0])  # softest (lowest limit) first
    print("=" * 70)
    print(" PINNACLE SOFTNESS RANK  (low maxRiskStake = softer market = more edge)")
    print("=" * 70)
    if not rows:
        print(" No moneyline limits available right now.")
        return
    print(f"{'maxRisk':>8}  match")
    print("-" * 70)
    for mr, match, league in rows[:25]:
        print(f"{mr:>8}  {match[:46]:46} {league[:18]}")
    import statistics
    med = statistics.median(r[0] for r in rows)
    print("-" * 70)
    print(f" {len(rows)} fixtures | median maxRisk {med:.0f} | "
          f"softest decile <= {sorted(r[0] for r in rows)[max(0,len(rows)//10)]:.0f}")
    print(" Concentrate steam / line-shop capital on the LOW-limit fixtures.")


if __name__ == "__main__":
    main()
