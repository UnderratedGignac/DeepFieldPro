import os
import sys
import sqlite3
import json
import math
import datetime
import logging
import pandas as pd
import pickle

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.model_runner import load_models, get_player_historical_stats, build_feature_vector
from src.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def compute_ev(FairProb_P: float, RawOdds_P: float) -> float:
    return (FairProb_P * (RawOdds_P - 1)) - (1 - FairProb_P)

def run_single_bet_predictor(BankrollSize_P: float):
    db_path = os.path.join(BASE_DIR, 'data', 'odds_stream.db')
    if not os.path.exists(db_path):
        logger.error("odds_stream.db not found. Did the scraper run?")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.market_id, m.fixture_id, m.market_name, m.selection_name, m.raw_odds, m.prop_player, m.prop_type, m.prop_line,
               f.home_team, f.away_team, f.kickoff_time, f.league_id
        FROM market m
        JOIN fixture f ON m.fixture_id = f.fixture_id
    """)
    rows = cursor.fetchall()
    conn.close()

    models = load_models()
    
    scaler_path = os.path.join(BASE_DIR, 'models', 'platt_scaler_sot.pkl')
    platt_scaler = None
    if os.path.exists(scaler_path):
        with open(scaler_path, 'rb') as f:
            platt_scaler = pickle.load(f)

    bets = []

    for row in rows:
        MarketId_V, FixtureId_V, MarketName_V, SelectionName_V, RawOdds_V, PlayerName_V, PropType_V, Line_V, HomeTeam_V, AwayTeam_V, KickoffTime_V, LeagueId_V = row
        
        if RawOdds_V < 1.20 or RawOdds_V > 15.0:
            continue
            
        FairProb_V = None
        IsFallback_V = False
        Confidence_V = "HIGH"
        
        if PlayerName_V:
            # Player Prop Market
            stats = get_player_historical_stats(PlayerName_V, FallbackPosition_P="FW", FallbackLeague_P="International")
            if stats is None:
                continue
                
            if stats.get('is_fallback'):
                IsFallback_V = True
                Confidence_V = "LOW"
                
            CompetitionType_V = 1 if "World Cup" in LeagueId_V or "International" in LeagueId_V else 0
            
            # Simple mock of opp profile
            opp_profile = {'ppda': 12.0, 'opp_possession_allowed': 50.0}
            features = build_feature_vector(stats, opp_profile)
            X_passes = pd.DataFrame([features], columns=['Age', 'Position_encoded', 'Minutes Played', 'Mn/Start', 'Percentage of Minutes Played', 'Crs', 'Interceptions', 'Tackles Won', 'ppda', 'opp_possession_allowed', 'sample_weight'])
            X_minutes = pd.DataFrame([features], columns=['Age', 'Starts', 'Percentage of Minutes Played', 'Mn/Start', 'Mn/MP', 'PPM', 'ppda', 'opp_possession_allowed', 'sample_weight'])
            
            ExpectedMinutes_V = float(models['min_p50'].predict(X_minutes)[0])
            
            if CompetitionType_V == 1:
                SotMean_V = float(models['sot_intl'].predict(X_passes)[0])
                IntlPpdaNorm_V = opp_profile['ppda'] / 9.5
                IntlMinutesFactor_V = 0.88
            else:
                SotMean_V = float(models['sot_club'].predict(X_passes)[0])
                IntlPpdaNorm_V = opp_profile['ppda'] / 12.0
                IntlMinutesFactor_V = 1.0
                
            LamSot_V = max(0.001, (SotMean_V / 90.0) * ExpectedMinutes_V * IntlPpdaNorm_V * IntlMinutesFactor_V)
            
            # Use poisson CDF for 'Over'
            if "Over" in SelectionName_V:
                RawProb_V = 1.0 - sum((math.exp(-LamSot_V) * (LamSot_V ** k)) / math.factorial(k) for k in range(math.floor(Line_V) + 1))
            else:
                RawProb_V = sum((math.exp(-LamSot_V) * (LamSot_V ** k)) / math.factorial(k) for k in range(math.floor(Line_V) + 1))
                
            if platt_scaler:
                FairProb_V = float(platt_scaler.predict_proba([[RawProb_V]])[0][1])
            else:
                FairProb_V = RawProb_V
                
        else:
            # Match Result / BTTS / Over-Under - Simplified Poisson logic
            HomeGoalLam_V = 1.5
            AwayGoalLam_V = 1.2
            if "Home Win" in SelectionName_V:
                FairProb_V = 0.45
            elif "BTTS" in MarketName_V:
                FairProb_V = (1 - math.exp(-HomeGoalLam_V)) * (1 - math.exp(-AwayGoalLam_V))
            else:
                FairProb_V = 0.50

        if FairProb_V is None: continue

        Ev_V = compute_ev(FairProb_V, RawOdds_V)
        
        if Ev_V >= 0.05 and FairProb_V >= 0.40:
            Status_V = "BATCH"
        elif 0.02 <= Ev_V < 0.05:
            Status_V = "MONITOR"
        else:
            Status_V = "SKIP"
            
        FullKelly_V = (FairProb_V * RawOdds_V - 1) / (RawOdds_V - 1) if RawOdds_V > 1 else 0
        KellyStake_V = (FullKelly_V / 4.0) * BankrollSize_P
        
        # Hard caps
        max_stake = BankrollSize_P * 0.05
        if IsFallback_V: max_stake = BankrollSize_P * 0.02
        KellyStake_V = max(0.0, min(KellyStake_V, max_stake))
        
        # Only assign stake to BATCH bets
        if Status_V != "BATCH":
            KellyStake_V = 0.0
            
        StakePct_V = (KellyStake_V / BankrollSize_P) * 100 if BankrollSize_P > 0 else 0
        
        bets.append({
            "fixture": f"{HomeTeam_V} vs {AwayTeam_V}",
            "kickoff": KickoffTime_V,
            "market": MarketName_V,
            "selection": SelectionName_V,
            "fair_prob": round(FairProb_V, 3),
            "raw_odds": RawOdds_V,
            "ev": round(Ev_V, 3),
            "kelly_stake": round(KellyStake_V, 2),
            "stake_pct": round(StakePct_V, 2),
            "confidence": Confidence_V,
            "is_fallback": IsFallback_V,
            "status": Status_V
        })
        
    bets.sort(key=lambda x: x['ev'], reverse=True)
    
    # Add rank
    for i, b in enumerate(bets):
        b['rank'] = i + 1
        
    output_data = {
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "bankroll": BankrollSize_P,
        "bets": bets
    }
    
    out_path = os.path.join(BASE_DIR, 'data', 'todays_single_bets.json')
    with open(out_path, 'w') as f:
        json.dump(output_data, f, indent=4)
        
    logger.info(f"Generated single predictions for {len(bets)} markets.")

if __name__ == "__main__":
    bankroll = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    run_single_bet_predictor(bankroll)
