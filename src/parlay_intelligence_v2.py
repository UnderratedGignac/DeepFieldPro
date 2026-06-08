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
    score = 30.0
    if has_lineup: score += 20.0
    prob = selection.get("prob", 0)
    score += (prob / 100.0) * 20.0
    ev = selection.get("ev", 0)
    if ev > 0: score += min(20.0, ev * 1.5) 
    elif ev < -5: score -= 10.0
    if selection.get("recommended"): score += 15.0
    seed = hashlib.md5(f"{selection.get('selection','')}{selection.get('odds',0)}".encode()).hexdigest()
    score += (int(seed[:2], 16) / 255.0) * 5.0
    return round(min(100.0, score), 2)

def get_current_bankroll():
    bankroll_db = os.path.join(BASE_DIR, "data", "bankroll.db")
    if os.path.exists(bankroll_db):
        try:
            import sqlite3
            conn = sqlite3.connect(bankroll_db)
            cursor = conn.cursor()
            cursor.execute("SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row and row[0] > 0: return row[0]
        except: pass
    return 1000.0

def build_smart_parlays():
    if not os.path.exists(DASHBOARD_FILE): return
    with open(DASHBOARD_FILE, "r") as f: dashboard_data = json.load(f)
    bankroll = get_current_bankroll()

    candidate_legs = []
    for match in dashboard_data:
        if match.get("status_code", "NS") != "NS": continue
        prediction = match.get("prediction")
        if not prediction or "markets" not in prediction: continue
        has_lineup = match.get("has_lineup", False)
        
        for market_type, selections in prediction["markets"].items():
            for sel in selections:
                prob = sel.get("prob", 0)
                if prob > 85: continue # Skip ultra-low odds "locks" for parlays
                if prob < 15: continue # Skip ultra-longshots for parlays
                
                odds = sel.get("odds")
                is_estimated = False
                if odds is None or odds <= 1.15:
                    # Estimate odds with 7% vig (generous)
                    odds = (1.0 / (prob / 100.0)) * 0.93
                    is_estimated = True
                
                if odds < 1.20: continue # Floor for leg odds
                
                trust = calculate_trust_score(sel, has_lineup)
                if is_estimated: trust -= 5.0
                
                candidate_legs.append({
                    "fixture": match["match"], "fixture_id": match["fixture_id"],
                    "market": market_type, "selection": sel["selection"],
                    "odds": odds, "prob": prob / 100.0,
                    "ev": sel.get("ev", -5.0 if is_estimated else 0),
                    "trust_score": trust
                })

    # Diversity: Sort and take best per match
    candidate_legs.sort(key=lambda x: (x["trust_score"], x["ev"]), reverse=True)
    top_candidates = []
    seen_fixtures = {}
    for leg in candidate_legs:
        f_id = leg["fixture_id"]
        seen_fixtures[f_id] = seen_fixtures.get(f_id, 0) + 1
        if seen_fixtures[f_id] <= 2: top_candidates.append(leg)
        if len(top_candidates) >= 60: break

    all_possible_parlays = []
    # Include 2, 3, and 4-leg parlays for "more odds"
    for size in [2, 3, 4]:
        # Limit search space for larger parlays
        pool = top_candidates[:30] if size > 2 else top_candidates
        for combo in itertools.combinations(pool, size):
            fixture_ids = [leg["fixture_id"] for leg in combo]
            if len(set(fixture_ids)) != len(fixture_ids): continue
            
            total_odds = 1.0
            total_fair_prob = 1.0
            avg_trust = 0.0
            for leg in combo:
                total_odds *= leg["odds"]
                total_fair_prob *= leg["prob"]
                avg_trust += leg["trust_score"]
            
            avg_trust /= size
            combined_ev = (total_fair_prob * total_odds) - 1.0
            # Scale trust by size (variance penalty)
            parlay_trust = avg_trust * (0.92 ** (size - 1))
            
            if total_odds < 2.5: continue # Target higher odds
            
            stake_pct = (parlay_trust / 100.0) * 0.015 * (1 + max(0, combined_ev))
            
            all_possible_parlays.append({
                "legs": [{"match": leg["fixture"], "selection": leg["selection"], "market": leg["market"], "odds": round(leg["odds"], 2), "trust": leg["trust_score"]} for leg in combo],
                "total_odds": round(total_odds, 2),
                "combined_ev": round(combined_ev * 100, 2),
                "parlay_trust_score": round(parlay_trust, 2),
                "recommended_stake": max(10.0, round(bankroll * stake_pct, 2)),
                "size": size
            })

    # Priority: 
    # 1. High Odds (5.0+) with Positive EV
    # 2. Mid Odds (2.5-5.0) with Positive EV
    # 3. High Odds with Neutral EV
    
    tier1 = [p for p in all_possible_parlays if p["combined_ev"] > 0 and p["total_odds"] >= 5.0]
    tier2 = [p for p in all_possible_parlays if p["combined_ev"] > 0 and p["total_odds"] >= 2.5]
    tier3 = [p for p in all_possible_parlays if p["combined_ev"] > -5 and p["total_odds"] >= 5.0]
    
    final_pool = tier1 + tier2 + tier3
    if not final_pool: final_pool = all_possible_parlays
    
    final_pool.sort(key=lambda x: (x["combined_ev"], x["total_odds"]), reverse=True)

    # STRICT DIVERSITY FILTER
    final_parlays = []
    seen_combos = set()
    global_match_usage = {}
    
    for p in final_pool:
        key = tuple(sorted([f"{l['match']}|{l['selection']}" for l in p['legs']]))
        if key in seen_combos: continue
        
        # Check if this parlay uses too many matches that are already heavily featured in the list
        matches = [l['match'] for l in p['legs']]
        skip = False
        for m in matches:
            if global_match_usage.get(m, 0) >= 3: # Max 3 appearances per match across the WHOLE list
                skip = True
                break
        if skip: continue
        
        final_parlays.append(p)
        seen_combos.add(key)
        for m in matches:
            global_match_usage[m] = global_match_usage.get(m, 0) + 1
            
        if len(final_parlays) >= 10: break

    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "bankroll_used": bankroll, "top_parlays": final_parlays}
    with open(OUTPUT_FILE, "w") as f: json.dump(output, f, indent=4)
    logger.info(f"Generated {len(final_parlays)} parlays with increased odds and variety.")

if __name__ == "__main__":
    build_smart_parlays()
