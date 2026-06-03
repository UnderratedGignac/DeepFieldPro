import os
import sys
import pandas as pd
from sklearn.linear_model import LogisticRegression
import pickle
import math
import logging

sys.path.insert(0, os.path.dirname(__file__))
from model_runner import load_models, build_feature_vector, get_player_historical_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCH_LOGS_CSV = os.path.join(BASE_DIR, "data", "world_cup_players_match_logs.csv")
MODEL_DIR = os.path.join(BASE_DIR, "models")

def train_platt_scaler(num_slates=30):
    logger.info("Rebuilding backtest results for Platt scaler training...")
    df = pd.read_csv(MATCH_LOGS_CSV)
    models = load_models()
    
    unique_games = df['game_id_'].dropna().unique()
    games_to_test = unique_games[:num_slates]
    
    results = []
    
    for game_id in games_to_test:
        game_logs = df[df['game_id_'] == game_id]
        
        for _, row in game_logs.iterrows():
            player_name = row['player_']
            actual_sot = float(row.get('Performance_SoT', 0) if pd.notna(row.get('Performance_SoT')) else 0)
            
            stats = get_player_historical_stats(player_name, FallbackPosition_P="FW", FallbackLeague_P="International")
            if stats is None:
                continue
                
            opp_profile = {'ppda': 12.0, 'opp_possession_allowed': 50.0}
            features = build_feature_vector(stats, opp_profile)
            
            MINUTES_FEATURES = ['Age', 'Starts', 'Percentage of Minutes Played', 'Mn/Start', 'Mn/MP', 'PPM', 'ppda', 'opp_possession_allowed', 'sample_weight']
            PASSES_FEATURES = ['Age', 'Position_encoded', 'Minutes Played', 'Mn/Start', 'Percentage of Minutes Played', 'Crs', 'Interceptions', 'Tackles Won', 'ppda', 'opp_possession_allowed', 'sample_weight']
            
            X_minutes = pd.DataFrame([features], columns=MINUTES_FEATURES)
            X_passes = pd.DataFrame([features], columns=PASSES_FEATURES)
            
            try:
                MinP50_V = float(models['min_p50'].predict(X_minutes)[0])
                SotMean_V = float(models['sot_intl'].predict(X_passes)[0])
                
                IntlPpdaNorm_V = opp_profile['ppda'] / 9.5
                IntlMinutesFactor_V = 0.88
                ExpectedMinutes_V = MinP50_V * IntlMinutesFactor_V
                
                LamSot_V = max(0.001, (SotMean_V / 90.0) * ExpectedMinutes_V * IntlPpdaNorm_V)
                RawProb_V = 1.0 - math.exp(-LamSot_V)
                
                hit = 1 if actual_sot >= 0.5 else 0
                
                results.append({
                    'raw_prob': RawProb_V,
                    'actual_hit': hit
                })
            except Exception:
                continue
                
    res_df = pd.DataFrame(results)
    
    X = res_df[['raw_prob']].values
    y = res_df['actual_hit'].values
    
    logger.info(f"Training Platt scaler on {len(X)} samples...")
    scaler = LogisticRegression(C=1.0)
    scaler.fit(X, y)
    
    out_path = os.path.join(MODEL_DIR, 'platt_scaler_sot.pkl')
    with open(out_path, 'wb') as f:
        pickle.dump(scaler, f)
        
    logger.info(f"Platt scaler saved to {out_path}")
    
    # Calculate before/after Brier
    brier_before = ((res_df['raw_prob'] - res_df['actual_hit']) ** 2).mean()
    calibrated_probs = scaler.predict_proba(X)[:, 1]
    brier_after = ((calibrated_probs - res_df['actual_hit']) ** 2).mean()
    
    print("\n" + "="*50)
    print("=== PLATT SCALING CALIBRATION SUMMARY ===")
    print("="*50)
    print(f"Samples Processed: {len(X)}")
    print(f"Brier Score (Before): {brier_before:.4f}")
    print(f"Brier Score (After):  {brier_after:.4f}")
    print("="*50)

if __name__ == "__main__":
    train_platt_scaler()
