import os
import json
import itertools
import logging
import hashlib
from datetime import datetime, timezone
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_FILE = os.path.join(BASE_DIR, "data", "todays_dashboard_state.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "smart_parlays.json")


def calculate_trust_score(selection: Dict, has_lineup: bool) -> float:
    """
    Enhanced Trust Score: Prioritizes Value (EV) and Lineup confirmation.
    """
    score = 20.0  # Base
    if has_lineup:
        score += 25.0  # High bonus for lineups

    prob = selection.get("prob", 0)
    score += (prob / 100.0) * 15.0

    # VALUE WEIGHTING: EV is now the strongest driver of trust
    ev = selection.get("ev", 0)
    if ev >= 0.15:
        score += 30.0  # Huge bonus for high value
    elif ev > 0.05:
        score += 15.0
    elif ev < 0:
        score -= 15.0

    if selection.get("recommended"):
        score += 10.0

    # Small randomness factor
    seed = hashlib.md5(
        f"{selection.get('selection','')}{selection.get('odds',0)}".encode()
    ).hexdigest()
    score += (int(seed[:2], 16) / 255.0) * 5.0

    return round(min(100.0, score), 2)


def get_current_bankroll():
    bankroll_db = os.path.join(BASE_DIR, "data", "bankroll.db")
    if os.path.exists(bankroll_db):
        try:
            import sqlite3

            conn = sqlite3.connect(bankroll_db)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()
            if row and row[0] > 0:
                return row[0]
        except:
            pass
    return 1000.0


def build_smart_parlays():
    if not os.path.exists(DASHBOARD_FILE):
        logger.warning(f"Dashboard file {DASHBOARD_FILE} not found.")
        return

    try:
        with open(DASHBOARD_FILE, "r") as f:
            dashboard_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load dashboard data: {e}")
        return

    bankroll = get_current_bankroll()

    candidate_legs = []
    for match in dashboard_data:
        if match.get("status_code", "NS") not in ["NS", "TBD"]:
            continue
        prediction = match.get("prediction")
        if not prediction or "markets" not in prediction:
            continue
        has_lineup = match.get("has_lineup", False)

        # PRE-FILTER: Only consider matches with lineups for higher trust parlays
        if not has_lineup:
            continue

        match_legs = []
        for market_type, selections in prediction["markets"].items():
            for sel in selections:
                prob = sel.get("prob", 0)
                if prob > 85:
                    continue  # Avoid low-odds legs that don't add value
                if prob < 20:
                    continue  # Avoid ultra-lottery legs

                odds = sel.get("odds")
                is_estimated = False
                if odds is None or odds <= 1.05:
                    # Estimate odds with 10% vig for safety in parlays
                    odds = (1.0 / (prob / 100.0)) * 0.90
                    is_estimated = True

                if odds < 1.50:
                    continue  # Prefer meaningful legs

                ev = (prob / 100.0) * odds - 1.0
                trust = calculate_trust_score(
                    {
                        "prob": prob,
                        "ev": ev,
                        "selection": sel["selection"],
                        "recommended": sel.get("recommended"),
                    },
                    has_lineup,
                )
                if is_estimated:
                    trust -= 10.0

                match_legs.append(
                    {
                        "fixture": match["match"],
                        "fixture_id": match["fixture_id"],
                        "market": market_type,
                        "selection": sel["selection"],
                        "odds": odds,
                        "prob": prob / 100.0,
                        "ev": ev,
                        "trust_score": trust,
                    }
                )

        # Diversity: Only take the SINGLE BEST (Highest EV/Trust) leg per match
        if match_legs:
            match_legs.sort(key=lambda x: (x["ev"], x["trust_score"]), reverse=True)
            candidate_legs.append(match_legs[0])

    # Sort candidates by overall quality
    candidate_legs.sort(key=lambda x: x["trust_score"], reverse=True)
    top_candidates = candidate_legs[:40]

    all_possible_parlays = []
    # Focus on 2 and 3-leg parlays for "Value Chaser" balance
    for size in [2, 3]:
        pool = top_candidates[:20] if size == 3 else top_candidates
        for combo in itertools.combinations(pool, size):
            total_odds = 1.0
            total_fair_prob = 1.0
            avg_trust = 0.0
            for leg in combo:
                total_odds *= leg["odds"]
                total_fair_prob *= leg["prob"]
                avg_trust += leg["trust_score"]

            avg_trust /= size
            combined_ev = (total_fair_prob * total_odds) - 1.0
            # Scale trust by size
            parlay_trust = avg_trust * (0.90 ** (size - 1))

            # VALUE CHASER TARGET: Min 4.0 odds for parlays to make it worth it
            if total_odds < 4.0:
                continue
            if combined_ev < 0.10:
                continue  # Min 10% Combined EV for parlays

            # Dynamic sizing based on EV and Trust
            stake_pct = (parlay_trust / 100.0) * 0.02 * (1 + combined_ev)

            all_possible_parlays.append(
                {
                    "legs": [
                        {
                            "match": leg["fixture"],
                            "selection": leg["selection"],
                            "market": leg["market"],
                            "odds": round(leg["odds"], 2),
                            "trust": round(leg["trust_score"], 1),
                        }
                        for leg in combo
                    ],
                    "total_odds": round(total_odds, 2),
                    "combined_ev": round(combined_ev * 100, 2),
                    "parlay_trust_score": round(parlay_trust, 2),
                    "recommended_stake": max(10.0, round(bankroll * stake_pct, 2)),
                    "size": size,
                    "fair_prob": round(total_fair_prob, 4),
                }
            )

    # Rank by EV and Trust
    all_possible_parlays.sort(
        key=lambda x: (x["combined_ev"], x["parlay_trust_score"]), reverse=True
    )

    # Diversity Filter: Max 2 appearances per match in the final list
    final_parlays = []
    global_match_usage = {}

    for p in all_possible_parlays:
        matches = [l["match"] for l in p["legs"]]
        if any(global_match_usage.get(m, 0) >= 2 for m in matches):
            continue

        final_parlays.append(p)
        for m in matches:
            global_match_usage[m] = global_match_usage.get(m, 0) + 1

        if len(final_parlays) >= 8:
            break

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bankroll_used": bankroll,
        "top_parlays": final_parlays,
        "strategy": "Value Chaser V2",
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=4)
    logger.info(f"Generated {len(final_parlays)} Value-Chaser parlays.")

    # Massive Parlay Edge Alert
    for p in final_parlays:
        if p["combined_ev"] >= 100.0:  # If the parlay edge is >= 100%
            try:
                from src.services.alerting import notifier

                alert_msg = (
                    f"🚨 *MASSIVE PARLAY EDGE ALERT (+{p['combined_ev']}% EV)* 🚨\n\n"
                )
                alert_msg += f"*{p['size']}-LEG SMART PARLAY*\n"
                alert_msg += f"*Total Odds:* {p['total_odds']}\n"
                alert_msg += f"*Recommended Stake:* ${p['recommended_stake']:.2f}\n\n"
                for leg in p["legs"]:
                    alert_msg += (
                        f"✅ {leg['match']} - {leg['selection']} @ {leg['odds']}\n"
                    )
                alert_msg += (
                    "\n_The AI just discovered this mispriced parlay combination!_"
                )

                if hasattr(notifier, "_send_whatsapp"):
                    notifier._send_whatsapp(alert_msg)
                else:
                    notifier.send_general_alert("Massive Parlay Edge Alert", alert_msg)
            except Exception as e:
                logger.error(f"Failed to send massive parlay alert: {e}")


if __name__ == "__main__":
    build_smart_parlays()
