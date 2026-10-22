"""
edge_status.py - "Are we allowed to bet real money yet?" decision gate.
=======================================================================
The honest lesson from this project's own backtests: realized P&L on a few
hundred bets is mostly noise, and the ONLY trustworthy leading indicator of a
real edge is CLV (Closing Line Value) - did we consistently beat the price the
market closed at? A strategy that beats the close is +EV long before win/loss
confirms it; one that doesn't is -EV no matter how good a hot streak looks.

This tool reads bet_log.db, isolates each real-money-candidate strategy
(model '1X2' and steam '1X2'), and prints a GO / LEAN / WAIT / NO-GO verdict
for whether that strategy has *earned* real-money status on Betarabia.

It is a READ-ONLY report. It changes nothing and places nothing. Use it as the
gate: keep Betarabia in shadow/paper until a strategy prints GO here.

Run:  .venv\\Scripts\\python.exe tools\\edge_status.py
"""

import os
import math
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")

# --- Readiness thresholds (deliberately conservative) ----------------------
MIN_SETTLED_WITH_CLV = 100  # CLV stabilizes around here; fewer = still noise
Z = 1.96  # 95% confidence
# Bets before this date were placed against STALE Betarabia odds (the scraper
# destroy-before-rebuild bug, fixed 2026-06-15) and/or hash-settled props, so their
# results are noise. The gate judges only the clean era. Bump this if a later data
# fix invalidates more history.
CLEAN_ERA_START = "2026-06-15"

# Only these (source, market) pairs are real-money candidates; market None means
# every market the strategy bets. Props stay off: the backtests showed them -EV.
CANDIDATES = [
    ("AI", "1X2", "Model 1X2 (Dixon-Coles)"),
    ("STEAM", "1X2", "Steam / line-movement 1X2"),
    ("SHARP", "1X2", "Sharp steam + Betarabia lag"),
    ("SHARPV", "1X2", "Value vs Pinnacle fair line"),
    ("VALUE_ONLY", None, "Value only - beats Pinnacle (1X2, O/U, BTTS)"),
    ("MODEL_VALUE_ALIGN", "Over/Under 2.5", "Model + value consensus O/U"),
]


def _settled(rows):
    return [
        r
        for r in rows
        if str(r.get("result", "")).upper() in ("W", "L", "WIN", "LOSS", "WON", "LOST")
    ]


def _mean_ci(values):
    """Mean and 95% normal-approx CI half-width for a list of numbers."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, float("inf")
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    half = Z * math.sqrt(var / n)
    return mean, half


def _roi(group):
    staked = sum(float(r.get("stake") or 0) for r in group)
    pnl = sum(float(r.get("pnl") or 0) for r in group)
    return (pnl / staked) if staked > 0 else 0.0, staked, pnl


def _verdict(n_clv, clv_mean, clv_lo):
    if n_clv < MIN_SETTLED_WITH_CLV:
        return (
            "WAIT",
            f"only {n_clv}/{MIN_SETTLED_WITH_CLV} settled bets have CLV - "
            f"too few to judge. Keep accumulating shadow data.",
        )
    if clv_lo > 0:
        return (
            "GO",
            "CLV is positive even at the 95% lower bound - a genuine, "
            "statistically-supported edge. Real money is justified.",
        )
    if clv_mean > 0:
        return (
            "LEAN",
            "average CLV is positive but not yet significant. Promising - "
            "keep accumulating; do NOT arm real money yet.",
        )
    return (
        "NO-GO",
        "CLV is <= 0 - you are not beating the close. This strategy is "
        "-EV; do NOT put real money on it regardless of recent P&L.",
    )


def main():
    if not os.path.exists(DB):
        print("bet_log.db not found.")
        return
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    all_rows = [dict(r) for r in con.execute("SELECT * FROM bet_log")]
    con.close()

    # Keep only clean-era bets (placed against fresh odds, real settlement).
    rows = [r for r in all_rows if str(r.get("placed_at", "")) >= CLEAN_ERA_START]
    excluded = len(all_rows) - len(rows)

    print("=" * 70)
    print(" EDGE-READINESS GATE  -  may we bet real money on Betarabia yet?")
    print(
        f" Rule: need >= {MIN_SETTLED_WITH_CLV} settled bets w/ CLV, and CLV > 0 at 95% CI."
    )
    print(
        f" Clean era >= {CLEAN_ERA_START}  ({excluded} pre-fix bets excluded as noise)."
    )
    print("=" * 70)

    any_go = False
    for src, mkt, label in CANDIDATES:
        grp = [
            r
            for r in rows
            if r.get("bet_source") == src and (mkt is None or r.get("market_type") == mkt)
        ]
        settled = _settled(grp)
        # PRIMARY scoreboard = CLV vs Pinnacle's FAIR (de-vigged) close
        # (pinnacle_fair_clv, written by settlement). The raw-close pinnacle_clv keeps
        # Pinnacle's margin and flatters every bet (+9.1% raw vs +1.4% fair for
        # VALUE_ONLY on 2026-10-21), so it must not grade; nor the never-populated
        # clv_sharp. The Betarabia self-CLV (clv) is shown only as a diagnostic. The
        # verdict does NOT fall back to any of them when the fair CLV is missing.
        with_clv = [r for r in settled if r.get("pinnacle_fair_clv") is not None]
        clvs = [float(r["pinnacle_fair_clv"]) for r in with_clv]
        clv_mean, clv_half = _mean_ci(clvs)
        clv_lo = clv_mean - clv_half if clvs else 0.0
        beat = (sum(1 for v in clvs if v > 0) / len(clvs)) if clvs else 0.0
        self_clvs = [float(r["clv"]) for r in settled if r.get("clv") is not None]
        self_mean = (sum(self_clvs) / len(self_clvs)) if self_clvs else None
        roi, staked, pnl = _roi(settled)
        wr = (
            (
                sum(1 for r in settled if str(r["result"]).upper().startswith("W"))
                / len(settled)
            )
            if settled
            else 0.0
        )

        tag, why = _verdict(len(with_clv), clv_mean, clv_lo)
        any_go = any_go or tag == "GO"

        print(f"\n[{tag}]  {label}   (source={src})")
        print(f"   settled bets ........ {len(settled)}   (open excluded)")
        print(
            f"   with SHARP CLV ...... {len(with_clv)}   (vs Pinnacle's fair close - the real test)"
        )
        if clvs:
            ci = (
                f"(95% CI {clv_lo:+.2%} .. {clv_mean + clv_half:+.2%})"
                if math.isfinite(clv_half)
                else "(CI n/a - need >=2 bets)"
            )
            print(f"   avg SHARP CLV ....... {clv_mean:+.2%}   {ci}")
            print(f"   beat-close rate ..... {beat:.1%}")
        if self_mean is not None:
            print(
                f"   (self-CLV vs Betarabia: {self_mean:+.2%}  [diagnostic only, {len(self_clvs)} bets])"
            )
        print(
            f"   realized ROI ........ {roi:+.1%}   "
            f"(staked ${staked:,.0f}, pnl ${pnl:+,.0f})"
        )
        print(f"   win rate ............ {wr:.1%}")
        print(f"   -> {why}")

    print("\n" + "-" * 70)
    if any_go:
        print(" At least one strategy is GO. Real-money execution on Betarabia is")
        print(" statistically justified for that strategy - proceed to build/arm the")
        print(" placement tool behind its own confirm gate.")
    else:
        print(" No strategy is GO yet. Betarabia stays SHADOW/paper. This is the")
        print(" correct, money-preserving state until CLV proves an edge.")
    print("-" * 70)


if __name__ == "__main__":
    main()
