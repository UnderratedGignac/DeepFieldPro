"""
arb_detector.py — Arbitrage and near-arbitrage detector for 1X2 markets.

True arbitrage = guaranteed profit regardless of outcome.
Near-arb = one side priced above fair value at Pinnacle; lock in edge.

Works on any combination of Betarabia + Pinnacle + Betfair prices.
Results annotate dashboard cards (no actual bets placed — all SHADOW).

Arb math:
    arb_margin = 1/H + 1/D + 1/A        (< 1.0 = arb; e.g. 0.98 = 2% profit)
    return_pct  = (1 / arb_margin - 1) * 100

Near-arb: one selection's Betarabia price > Pinnacle's same selection by ≥2%.
This means the soft book is paying out more than the sharp market implies is fair.
"""

import logging

logger = logging.getLogger(__name__)

_MIN_ARB_RETURN = 0.5  # % minimum arb to flag (avoids noise)
_NEAR_ARB_THRESHOLD = 2.0  # % Betarabia must beat Pinnacle price to flag near-arb


def check_arb(best_prices: dict, pinnacle_prices: dict | None = None) -> dict:
    """
    Detect arbitrage and near-arbitrage conditions across available books.

    Args:
        best_prices: {"home": float, "draw": float, "away": float}
                     These are the BEST prices found across all books.
        pinnacle_prices: {"home": float, "draw": float, "away": float} or None
                         Raw Pinnacle odds (not de-vigged) — the sharpest reference.

    Returns:
        {
            "is_arb":        bool,   # true arb across best prices
            "arb_return_pct": float, # guaranteed return % if arb
            "near_arb":      list,   # selections where Betarabia > Pinnacle by ≥2%
            "arb_breakdown": dict,   # {H: pct, D: pct, A: pct} implied margins
            "status":        str,    # "ARB" | "NEAR-ARB" | "VALUE" | "NORMAL"
        }
    """
    result = {
        "is_arb": False,
        "arb_return_pct": 0.0,
        "near_arb": [],
        "arb_breakdown": {},
        "status": "NORMAL",
    }

    h = best_prices.get("home") or 0.0
    d = best_prices.get("draw") or 0.0
    a = best_prices.get("away") or 0.0

    if not (h > 1 and d > 1 and a > 1):
        return result

    impl_h = 1.0 / h
    impl_d = 1.0 / d
    impl_a = 1.0 / a
    margin = impl_h + impl_d + impl_a

    result["arb_breakdown"] = {
        "H": round(impl_h * 100, 2),
        "D": round(impl_d * 100, 2),
        "A": round(impl_a * 100, 2),
        "total": round(margin * 100, 2),
    }

    if margin < 1.0:
        ret_pct = (1.0 / margin - 1.0) * 100
        if ret_pct >= _MIN_ARB_RETURN:
            result["is_arb"] = True
            result["arb_return_pct"] = round(ret_pct, 2)
            result["status"] = "ARB"
            logger.info(
                f"[ARB] True arb detected! Return={ret_pct:.1f}% "
                f"(H={h} D={d} A={a})"
            )

    # Near-arb: check each selection vs Pinnacle
    if pinnacle_prices:
        ph = pinnacle_prices.get("home") or 0.0
        pd_ = pinnacle_prices.get("draw") or 0.0
        pa = pinnacle_prices.get("away") or 0.0
        comparisons = [
            ("H", best_prices.get("home") or 0, ph),
            ("D", best_prices.get("draw") or 0, pd_),
            ("A", best_prices.get("away") or 0, pa),
        ]
        for sel, best_p, pinn_p in comparisons:
            if best_p > 1 and pinn_p > 1:
                edge_pct = (best_p / pinn_p - 1.0) * 100
                if edge_pct >= _NEAR_ARB_THRESHOLD:
                    result["near_arb"].append(
                        {
                            "selection": sel,
                            "best_odds": best_p,
                            "pinnacle_odds": pinn_p,
                            "edge_pct": round(edge_pct, 1),
                        }
                    )

    if not result["is_arb"]:
        if result["near_arb"]:
            result["status"] = "NEAR-ARB"
        elif margin < 1.05:
            result["status"] = "VALUE"  # tight market, good pricing

    return result


def compute_arb_stakes(
    h_odds: float, d_odds: float, a_odds: float, total_stake: float = 100.0
) -> dict:
    """
    Compute how much to stake on each leg for a guaranteed return.
    Only meaningful when check_arb returns is_arb=True.

    Returns: {"stake_H": float, "stake_D": float, "stake_A": float,
              "profit": float, "return_pct": float}
    """
    if not (h_odds > 1 and d_odds > 1 and a_odds > 1):
        return {}
    margin = 1 / h_odds + 1 / d_odds + 1 / a_odds
    if margin >= 1.0:
        return {}
    guaranteed_return = total_stake / margin
    return {
        "stake_H": round(guaranteed_return / h_odds, 2),
        "stake_D": round(guaranteed_return / d_odds, 2),
        "stake_A": round(guaranteed_return / a_odds, 2),
        "profit": round(guaranteed_return - total_stake, 2),
        "return_pct": round((guaranteed_return / total_stake - 1) * 100, 2),
    }
