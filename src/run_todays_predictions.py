# -*- coding: utf-8 -*-
"""
run_todays_predictions.py — DeepFieldPro Master Pipeline Runner
================================================================
Executes end-to-end predictions for today's fixtures with international-aware models.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P  (e.g. Bankroll_P)
- Variables:  ProperCase suffix _V  (e.g. FairProb_V)
- SQL table/column names: lowercase
- SQL keywords: UPPERCASE
- Comments: single line, human-readable, max 1 line
"""

import os
import sys
import sqlite3
import pandas as pd
import pickle
import numpy as np
from scipy import stats
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.model_runner_v2 import get_player_historical_stats, load_models_international, build_feature_vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODELS_DIR = os.path.join(BASE_DIR, 'models')
ODDS_DB = os.path.join(DATA_DIR, 'odds_stream.db')


def load_platt_scaler():
    """Load Platt scaling calibration model if available."""
    scaler_path = os.path.join(MODELS_DIR, 'platt_scaler_sot.pkl')
    if os.path.exists(scaler_path):
        with open(scaler_path, 'rb') as f:
            return pickle.load(f)
    return None


def calculate_fair_prob_passes(player_name: str, threshold: float = 40.5) -> float:
    """Calculate fair probability for passes over market using historical stats."""
    Stats_P = get_player_historical_stats(player_name, competition_type=0)
    
    if Stats_P is None or len(Stats_P) == 0:
        return 0.5
    
    avg_passes = Stats_P.get('avg_passes', 35.0)
    std_passes = Stats_P.get('std_passes', 10.0)
    
    z_score = (threshold - avg_passes) / max(std_passes, 1.0)
    fair_prob = 1.0 - stats.norm.cdf(z_score)
    
    return float(np.clip(fair_prob, 0.05, 0.95))


def calculate_ev(fair_prob: float, odds: float) -> Optional[float]:
    """Calculate Expected Value from fair probability and decimal odds."""
    if odds is None or odds <= 1.0:
        return None
    ev = (fair_prob * (odds - 1)) - ((1 - fair_prob) * 1)
    return float(ev)


def kelly_stake(fair_prob: float, odds: float, bankroll: float, quarter_kelly: bool = True) -> float:
    """Calculate Kelly stake size."""
    if odds <= 1.0 or fair_prob <= 0:
        return 0.0
    
    b = odds - 1
    q = 1 - fair_prob
    kelly_fraction = (b * fair_prob - q) / b
    
    if kelly_fraction <= 0:
        return 0.0
    
    if quarter_kelly:
        kelly_fraction *= 0.25
    
    stake = bankroll * kelly_fraction
    max_stake = bankroll * 0.08
    return min(stake, max_stake)


def scan_odds_db() -> List[Dict[str, Any]]:
    """Scan odds_stream.db for available player markets."""
    if not os.path.exists(ODDS_DB):
        print(f"WARNING: Odds database not found: {ODDS_DB}")
        return []
    
    conn = sqlite3.connect(ODDS_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT DISTINCT 
        match_id,
        market_type,
        selection_name,
        price,
        bookmaker
    FROM odds_feed
    WHERE timestamp > datetime("now", "-7 days")
    ORDER BY match_id, market_type
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    opportunities = []
    for row in rows:
        match_id, market_type, selection_name, price, bookmaker = row
        
        if ' - ' not in selection_name:
            continue
        
        parts = selection_name.split(' - ')
        if len(parts) < 2:
            continue
        
        outcome = parts[0].strip()
        player_name = ' - '.join(parts[1:]).strip()
        
        if 'Over' not in outcome:
            continue
        
        opportunities.append({
            'match_id': match_id,
            'market_type': market_type,
            'player_name': player_name,
            'outcome': outcome,
            'odds': price,
            'bookmaker': bookmaker
        })
    
    return opportunities


def generate_predictions(bankroll: float = 500.0) -> List[Dict[str, Any]]:
    """Generate predictions for all available opportunities."""
    print("=" * 70)
    print("DeepFieldPro Prediction Engine — International Friendlies")
    print("=" * 70)
    print(f"Bankroll: ${bankroll:.2f}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()
    
    platt_scaler = load_platt_scaler()
    
    opportunities = scan_odds_db()
    print(f"Found {len(opportunities)} market opportunities in odds_stream.db")
    print()
    
    predictions = []
    
    for opp in opportunities:
        player_name = opp['player_name']
        market_type = opp['market_type']
        odds = opp['odds']
        
        print(f"Analyzing: {player_name} | {market_type} @ {odds:.2f}")
        
        fair_prob = None
        raw_prob = None
        
        if 'passes' in market_type:
            threshold = float(market_type.split('_')[-1])
            fair_prob = calculate_fair_prob_passes(player_name, threshold)
            raw_prob = fair_prob
        elif 'sot' in market_type.lower():
            try:
                Stats_P = get_player_historical_stats(player_name, competition_type=1)
                if Stats_P:
                    OppProfile_P = {'opp_ppda': 9.5, 'opp_possession': 50}
                    Features_V = build_feature_vector(Stats_P, OppProfile_P)
                    
                    models = load_models_international()
                    model = models.get('international', models.get('club'))
                    
                    if model:
                        raw_prob = float(model.predict_proba([Features_V])[0][1])
                        
                        if platt_scaler:
                            calib_input = np.array([[raw_prob]])
                            calibrated_probs = platt_scaler.predict_proba(calib_input)[0]
                            fair_prob = float(calibrated_probs[1])
                            
                            if fair_prob < 0.10 or fair_prob > 0.90:
                                print(f"  ⚠ LOW_CONFIDENCE: Calibrated prob {fair_prob:.3f} outside bounds")
                                continue
                        else:
                            fair_prob = raw_prob
            except Exception as e:
                print(f"  Error computing SoT prob: {e}")
                continue
        else:
            print(f"  Skipping unsupported market: {market_type}")
            continue
        
        if fair_prob is None:
            print(f"  Could not compute fair probability")
            continue
        
        ev = calculate_ev(fair_prob, odds)
        
        if ev is None or ev <= 0:
            print(f"  Fair Prob: {fair_prob:.3f} | EV: {ev:.4f} (NO BET)")
            continue
        
        stake = kelly_stake(fair_prob, odds, bankroll)
        
        if stake < bankroll * 0.01:
            print(f"  Fair Prob: {fair_prob:.3f} | EV: {ev:.4f} | Stake too small")
            continue
        
        print(f"  ✓ BET RECOMMENDED")
        print(f"    Fair Prob: {fair_prob:.3f} | Raw Prob: {raw_prob:.3f}")
        print(f"    EV: +{ev:.4f} ({ev*100:.1f}%)")
        print(f"    Stake: ${stake:.2f} ({stake/bankroll*100:.2f}% of bankroll)")
        print()
        
        predictions.append({
            'player_name': player_name,
            'market': market_type,
            'outcome': opp['outcome'],
            'odds': odds,
            'fair_prob': fair_prob,
            'raw_prob': raw_prob,
            'ev': ev,
            'stake': stake,
            'bookmaker': opp['bookmaker'],
            'match_id': opp['match_id'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    return predictions


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run DeepFieldPro predictions')
    parser.add_argument('--bankroll', type=float, default=500.0, help='Starting bankroll')
    args = parser.parse_args()
    
    predictions = generate_predictions(bankroll=args.bankroll)
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if len(predictions) == 0:
        print("No bets recommended at current odds.")
        print()
        print("Possible reasons:")
        print("  - No live odds in odds_stream.db")
        print("  - All EV calculations are negative or zero")
        print("  - Fair probabilities don't exceed threshold")
        print()
        print("Next steps:")
        print("  1. Run scraper: python src/data_acquisition/betarabia_scraper.py")
        print("  2. Wait for live odds to populate")
        print("  3. Re-run: python src/run_todays_predictions.py --bankroll 500")
    else:
        print(f"Total bets: {len(predictions)}")
        total_stake = sum(p['stake'] for p in predictions)
        avg_ev = sum(p['ev'] for p in predictions) / len(predictions)
        print(f"Total stake: ${total_stake:.2f}")
        print(f"Average EV: +{avg_ev:.4f} ({avg_ev*100:.1f}%)")
        print()
        print("Recommended Bets:")
        print("-" * 70)
        for i, pred in enumerate(predictions, 1):
            print(f"{i}. {pred['player_name']} | {pred['market']} | {pred['outcome']}")
            print(f"   Odds: {pred['odds']:.2f} | Fair: {pred['fair_prob']:.3f} | EV: +{pred['ev']:.4f}")
            print(f"   Stake: ${pred['stake']:.2f} | Book: {pred['bookmaker']}")
            print()
        
        print("=" * 70)
        print("DISCLAIMER: This is paper trading only. No real money involved.")
        print("Track CLV after settlement to verify edge.")
        print("=" * 70)
    
    return predictions


if __name__ == '__main__':
    main()
