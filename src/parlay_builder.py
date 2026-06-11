import os
import json
import itertools
import logging
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SINGLE_BETS_FILE = os.path.join(BASE_DIR, "data", "todays_single_bets.json")


def is_correlated(legs: List[Dict]) -> bool:
    """Check if any two legs are from the same fixture unless it's BTTS + Over 2.5"""
    fixtures = [leg["fixture"] for leg in legs]
    if len(set(fixtures)) == len(fixtures):
        return False  # All different fixtures, no correlation

    # There are matching fixtures. Check if it's the BTTS + Over 2.5 exception
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            if legs[i]["fixture"] == legs[j]["fixture"]:
                m1 = legs[i]["market"].lower()
                m2 = legs[j]["market"].lower()

                # Check if one is BTTS and other is Over 2.5
                is_btts_1 = "btts" in m1 or "both teams to score" in m1
                is_over25_1 = "over 2.5" in m1
                is_btts_2 = "btts" in m2 or "both teams to score" in m2
                is_over25_2 = "over 2.5" in m2

                if (is_btts_1 and is_over25_2) or (is_btts_2 and is_over25_1):
                    # Flag as CORRELATED_RISK, but we want to AVOID this per prompt ("avoid")
                    return True

                return True  # Correlated

    return False


def build_parlays():
    if not os.path.exists(SINGLE_BETS_FILE):
        logger.error(f"{SINGLE_BETS_FILE} not found. Run single predictor first.")
        return

    with open(SINGLE_BETS_FILE, "r") as f:
        data = json.load(f)

    bankroll = data.get("bankroll", 100.0)
    bets = data.get("bets", [])

    # STEP 1: Filter only BATCH bets
    batch_bets = [b for b in bets if b["status"] == "BATCH"]

    parlays = []

    # STEP 4: Build 2-leg and 3-leg combinations
    for combo_size in [2, 3]:
        for combo in itertools.combinations(batch_bets, combo_size):
            if is_correlated(combo):
                continue

            ParlayFairProb_V = 1.0
            ParlayOdds_V = 1.0
            HasFallbackLeg_V = False

            for leg in combo:
                ParlayFairProb_V *= leg["fair_prob"]
                ParlayOdds_V *= leg["raw_odds"]
                if leg.get("is_fallback"):
                    HasFallbackLeg_V = True

            ParlayEv_V = (ParlayFairProb_V * ParlayOdds_V) - 1.0

            # VALUE CHASER: Increased EV and Odds thresholds for parlays
            if ParlayEv_V >= 0.12 and ParlayOdds_V >= 4.0:
                FullKelly_V = (
                    (ParlayFairProb_V * ParlayOdds_V - 1) / (ParlayOdds_V - 1)
                    if ParlayOdds_V > 1
                    else 0
                )
                KellyStake_V = (FullKelly_V / 4.0) * bankroll

                # Hard caps
                max_stake = bankroll * 0.02
                if HasFallbackLeg_V:
                    max_stake = bankroll * 0.01

                KellyStake_V = max(0.0, min(KellyStake_V, max_stake))
                StakePct_V = (KellyStake_V / bankroll) * 100 if bankroll > 0 else 0

                parlay = {
                    "legs": [leg["selection"] for leg in combo],
                    "fixtures": [leg["fixture"] for leg in combo],
                    "parlay_odds": round(ParlayOdds_V, 2),
                    "parlay_fair_prob": round(ParlayFairProb_V, 3),
                    "parlay_ev": round(ParlayEv_V, 3),
                    "parlay_stake": round(KellyStake_V, 2),
                    "stake_pct": round(StakePct_V, 2),
                    "has_fallback_leg": HasFallbackLeg_V,
                    "status": "BATCH" if KellyStake_V > 0 else "SKIP",
                }

                if parlay["status"] == "BATCH":
                    parlays.append(parlay)

    # STEP 6: Rank parlays by ParlayEv_V descending and keep top 5
    parlays.sort(key=lambda x: x["parlay_ev"], reverse=True)
    top_parlays = parlays[:5]

    for i, p in enumerate(top_parlays):
        p["rank"] = i + 1

    # STEP 7: Append to todays_single_bets.json
    data["parlays"] = top_parlays
    with open(SINGLE_BETS_FILE, "w") as f:
        json.dump(data, f, indent=4)

    logger.info(f"Built {len(top_parlays)} top profitable parlays.")


if __name__ == "__main__":
    build_parlays()
