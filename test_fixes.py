import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from generate_predictions import generate_predictions
import json

def test_issues():
    # Run the generator
    generate_predictions()
    
    out_path = os.path.join(os.path.dirname(__file__), "data", "tomorrow_predictions_real.json")
    with open(out_path, "r") as f:
        data = json.load(f)
        
    print("\n" + "="*50)
    print("=== TEST 01: FLAT PROBABILITY FLOOR (Forwards) ===")
    print("="*50)
    
    # Extract forwards
    forwards = ["Chris Wood", "Rasmus Hojlund", "Yoane Wissa", "Armando Broja", "Robert Lewandowski"]
    for game in data:
        for p in game["player_projections"]:
            if p["player"] in forwards:
                # Get the fair probability for shots on target
                sot_prob = p["top_ev_play"]["fair_prob"] if p.get("top_ev_play") and "shots_on_target" in p["top_ev_play"]["market"] else p["expected_sot"]
                print(f"Player: {p['player']:<20} | SoT Fair Prob: {sot_prob}")
                
    print("\n" + "="*50)
    print("=== TEST 03: SIMULATED ODDS REMOVAL ===")
    print("="*50)
    for game in data:
        for p in game["player_projections"]:
            if p["player"] in forwards:
                top_play = p.get("top_ev_play")
                if top_play:
                    print(f"Player: {p['player']:<20} | EV: {top_play.get('expected_ev', 'null')} | Status: {top_play.get('status', 'WAITING_FOR_LIVE_ODDS')} | Target Odds: > {top_play.get('target_odds_threshold')}")

if __name__ == "__main__":
    test_issues()
