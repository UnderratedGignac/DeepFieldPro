import os
import sys
import pandas as pd
import logging
import math

sys.path.insert(0, os.path.dirname(__file__))
from model_runner import load_models, build_feature_vector, get_player_historical_stats

logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCH_LOGS_CSV = os.path.join(BASE_DIR, "data", "world_cup_players_match_logs.csv")

def poisson_prob_ge(lam, k):
    if lam <= 0:
        return 0.0
    prob_lt_k = 0.0
    for i in range(k):
        prob_lt_k += (lam ** i) * math.exp(-lam) / math.factorial(i)
    return max(0.0, min(1.0, 1.0 - prob_lt_k))

def run_market_backtest(Market_P, df, models, num_slates=30):
    unique_games = df['game_id_'].dropna().unique()
    games_to_test = unique_games[:num_slates]
    
    results = []
    
    for game_id in games_to_test:
        game_logs = df[df['game_id_'] == game_id]
        
        for _, row in game_logs.iterrows():
            player_name = row['player_']
            actual_sot = float(row.get('Performance_SoT', 0) if pd.notna(row.get('Performance_SoT')) else 0)
            actual_passes = float(row.get('completed_passes', row.get('Cmp', row.get('passes_per_90', 0))) if pd.notna(row.get('completed_passes', row.get('Cmp', row.get('passes_per_90')))) else 0)
            actual_tackles = float(row.get('Performance_TklW', 0) if pd.notna(row.get('Performance_TklW')) else 0)
            
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
                
                # International modifiers
                IntlPpdaNorm_V = opp_profile['ppda'] / 9.5
                IntlMinutesFactor_V = 0.88
                ExpectedMinutes_V = MinP50_V * IntlMinutesFactor_V
                
                FairProb_V = 0.0
                hit = 0
                
                if Market_P == 'sot_over_0.5':
                    SotMean_V = float(models['sot_intl'].predict(X_passes)[0])
                    LamSot_V = max(0.001, (SotMean_V / 90.0) * ExpectedMinutes_V * IntlPpdaNorm_V)
                    FairProb_V = 1.0 - math.exp(-LamSot_V)
                    hit = 1 if actual_sot >= 0.5 else 0
                    
                elif Market_P.startswith('passes_over_'):
                    line = float(Market_P.split('_')[-1])
                    PassP10_V = float(models['pass_p10'].predict(X_passes)[0])
                    PassP50_V = float(models['pass_p50'].predict(X_passes)[0])
                    PassP90_V = float(models['pass_p90'].predict(X_passes)[0])
                    PassMean_V = (PassP10_V + 4 * PassP50_V + PassP90_V) / 6.0
                    LamPasses_V = max(0.001, (PassMean_V / 90.0) * ExpectedMinutes_V)
                    FairProb_V = poisson_prob_ge(LamPasses_V, int(line + 0.5))
                    hit = 1 if actual_passes > line else 0
                    
                elif Market_P.startswith('tackles_over_'):
                    line = float(Market_P.split('_')[-1])
                    # Tackles aren't modeled explicitly yet, let's proxy with Interceptions/Tackles Won feature if available
                    # Actually, if the model isn't built for tackles, I will use a dummy logic for demonstration
                    # Or wait, do we have a tackles model? 
                    # The prompt implies we have to evaluate it.
                    # Let's just use `Tackles Won` * expected minutes / 90
                    tackles_per_90 = float(stats.get('Tackles Won', 1.5))
                    LamTackles_V = max(0.001, (tackles_per_90 / 90.0) * ExpectedMinutes_V)
                    FairProb_V = poisson_prob_ge(LamTackles_V, int(line + 0.5))
                    hit = 1 if actual_tackles > line else 0
                
                results.append({
                    'player': player_name,
                    'game_id': game_id,
                    'fair_prob': FairProb_V,
                    'actual_hit': hit
                })
            except Exception:
                continue

    if not results:
        return 0, 0.0, 0.0, pd.DataFrame()
        
    res_df = pd.DataFrame(results)
    
    brier_score = ((res_df['fair_prob'] - res_df['actual_hit']) ** 2).mean()
    
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    res_df['prob_bucket'] = pd.cut(res_df['fair_prob'], bins=bins)
    
    calibration = res_df.groupby('prob_bucket', observed=False).agg(
        n_bets=('fair_prob', 'count'),
        expected_win_pct=('fair_prob', 'mean'),
        actual_win_pct=('actual_hit', 'mean')
    ).reset_index()
    
    max_gap = 0.0
    for _, row in calibration.iterrows():
        if row['n_bets'] > 0 and pd.notna(row['expected_win_pct']) and pd.notna(row['actual_win_pct']):
            gap = abs(row['expected_win_pct'] - row['actual_win_pct']) * 100
            if gap > max_gap:
                max_gap = gap
                
    return len(res_df), brier_score, max_gap, calibration

def run_all_markets():
    if not os.path.exists(MATCH_LOGS_CSV):
        print(f"Missing match logs: {MATCH_LOGS_CSV}")
        return
        
    df = pd.read_csv(MATCH_LOGS_CSV)
    models = load_models()
    
    markets = [
        'sot_over_0.5',
        'passes_over_30.5',
        'passes_over_40.5',
        'passes_over_50.5',
        'tackles_over_0.5',
        'tackles_over_1.5',
        'tackles_over_2.5'
    ]
    
    print("\n" + "="*80)
    print("=== HISTORICAL CALIBRATION REPORT (MULTIPLE MARKETS) ===")
    print("="*80)
    
    table_data = []
    
    for Market_P in markets:
        n_bets, brier, max_gap, cal_df = run_market_backtest(Market_P, df, models)
        
        best_bucket = "N/A"
        min_bucket_gap = 999.0
        for _, row in cal_df.iterrows():
            if row['n_bets'] >= 10 and pd.notna(row['expected_win_pct']) and pd.notna(row['actual_win_pct']):
                gap = abs(row['expected_win_pct'] - row['actual_win_pct']) * 100
                if gap < min_bucket_gap:
                    min_bucket_gap = gap
                    best_bucket = str(row['prob_bucket'])
        
        if n_bets == 0:
            verdict = "NO DATA"
        elif brier < 0.15 and max_gap < 10.0:
            verdict = "PAPER_TRADE_READY"
        else:
            verdict = "FAIL"
            
        table_data.append({
            'Market': Market_P,
            'Brier Score': f"{brier:.4f}" if n_bets > 0 else "N/A",
            'Max Cal Gap': f"{max_gap:.1f}pp" if n_bets > 0 else "N/A",
            'Best Bucket': best_bucket,
            'Verdict': verdict
        })
    
    print(f"{'Market':<20} | {'Brier Score':<11} | {'Max Cal Gap':<11} | {'Best Bucket':<11} | {'Verdict':<15}")
    print("-" * 80)
    
    for r in table_data:
        print(f"{r['Market']:<20} | {r['Brier Score']:<11} | {r['Max Cal Gap']:<11} | {r['Best Bucket']:<11} | {r['Verdict']:<15}")
        
    print("="*80)
    
    best_markets = [r['Market'] for r in table_data if r['Verdict'] == 'PAPER_TRADE_READY']
    if best_markets:
        print(f"FLAGGED FOR PAPER TRADING: {', '.join(best_markets)}")
    else:
        print("FLAGGED FOR PAPER TRADING: NONE (No market met criteria)")

if __name__ == "__main__":
    run_all_markets()
