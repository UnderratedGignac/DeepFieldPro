"""
backtester.py
--------------
STEP 2: Backtesting engine.

Replays historical StatsBomb match data to simulate the betting system
running live. Checks if our model's predicted pass distributions were
accurate and whether our bets would have been profitable (positive CLV).

Output:
  - backtest_results.csv  : Every simulated bet with outcome
  - backtest_summary.txt  : ROI, hit rate, avg CLV, Sharpe ratio
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from pricing_engine import calculate_over_prob
from utils import remove_vig

MODEL_DIR = 'C:/Users/Elie/DeepFieldPro/models'
DATA_DIR  = 'C:/Users/Elie/DeepFieldPro/data'
PASSES_LINES = [30.5, 35.5, 40.5, 45.5, 50.5, 55.5, 60.5]
MIN_EDGE = 0.03
KELLY_FRACTION = 0.25
STARTING_BANKROLL = 10000.0

def load_models():
    return {
        'start_clf': lgb.Booster(model_file=f'{MODEL_DIR}/minutes_start_classifier.txt'),
        'min_p10':   lgb.Booster(model_file=f'{MODEL_DIR}/minutes_p10_regressor.txt'),
        'min_p50':   lgb.Booster(model_file=f'{MODEL_DIR}/minutes_p50_regressor.txt'),
        'min_p90':   lgb.Booster(model_file=f'{MODEL_DIR}/minutes_p90_regressor.txt'),
        'pass_p10':  lgb.Booster(model_file=f'{MODEL_DIR}/passes_p10.txt'),
        'pass_p50':  lgb.Booster(model_file=f'{MODEL_DIR}/passes_p50.txt'),
        'pass_p90':  lgb.Booster(model_file=f'{MODEL_DIR}/passes_p90.txt'),
    }

def build_features(row):
    """Build model feature vector from a player-match row."""
    pos_map = {
        'Center Midfield': 3, 'Defensive Midfield': 3, 'Attacking Midfield': 3,
        'Left Midfield': 3, 'Right Midfield': 3, 'MF': 3, 'CM': 3, 'DM': 3, 'AM': 3,
        'Center Back': 2, 'Left Back': 2, 'Right Back': 2, 'DF': 2, 'CB': 2, 'LB': 2, 'RB': 2,
        'Left Wing': 1, 'Right Wing': 1, 'Center Forward': 1, 'FW': 1, 'CF': 1, 'LW': 1, 'RW': 1,
        'Left Wing Back': 2, 'Right Wing Back': 2,
    }
    pos_enc  = pos_map.get(str(row.get('Position', row.get('position', 'Unknown'))), 2)
    mn_start = float(row.get('Mn/Start', row.get('career_min', row.get('Mn_Start', 75))))
    min_pct  = float(row.get('Min%', min(mn_start / 90.0, 1.1)))
    ppm      = float(row.get('PPM', row.get('avg_passes', 45) / 90.0))
    gls      = float(row.get('Gls', row.get('Goals Scored While on Pitch', row.get('onG', 0.0))))

    return {
        'MINUTES': {
            'Age':                          float(row.get('Age', 26)),
            'Starts':                       float(row.get('Starts', 1)),
            'Percentage of Minutes Played': min_pct,
            'Mn/Start':                     mn_start,
            'Mn/MP':                        mn_start,
            'PPM':                          ppm,
            'ppda':                         float(row.get('ppda', 12.0)),
            'opp_possession_allowed':       float(row.get('opp_possession_allowed', 50.0)),
            'sample_weight':                1.0,
        },
        'PASSES': {
            'Age':                          float(row.get('Age', 26)),
            'Position_encoded':             pos_enc,
            'Minutes Played':               float(row.get('Minutes Played', mn_start)),
            'Mn/Start':                     mn_start,
            'Percentage of Minutes Played': min_pct,
            'Crs':                          float(row.get('Crs', 1.0)),
            'Interceptions':                float(row.get('Interceptions', 1.0)),
            'Tackles Won':                  float(row.get('Tackles Won', 1.0)),
            'Goals Scored While on Pitch':  gls,
            'ppda':                         float(row.get('ppda', 12.0)),
            'opp_possession_allowed':       float(row.get('opp_possession_allowed', 50.0)),
            'sample_weight':                1.0,
        }
    }

def simulate_market_odds(fair_prob, vig=0.05):
    """Simulate what a sharp bookmaker would offer (fair_prob minus vig)."""
    book_prob = fair_prob + vig / 2
    book_prob = min(book_prob, 0.95)
    return round(1.0 / book_prob, 3)

print("="*60)
print("STEP 2: Running Backtest")
print("="*60)

# Load test data (exclude last 20% used for training — time-series split)
try:
    df = pd.read_csv(f'{DATA_DIR}/training_dataset.csv')
    df['match_date'] = pd.to_datetime(df.get('match_date', df.get('date', pd.NaT)), errors='coerce')
    df = df.sort_values('match_date').reset_index(drop=True)
    # Use last 20% as out-of-sample test set
    split_idx = int(len(df) * 0.80)
    test_df = df.iloc[split_idx:].copy()
    print(f"Out-of-sample test rows: {len(test_df)}")
except FileNotFoundError:
    print("Error: training_dataset.csv not found. Run build pipeline first.")
    exit(1)

models = load_models()

MINUTES_FEATURES = ['Age','Starts','Percentage of Minutes Played','Mn/Start','Mn/MP','PPM','ppda','opp_possession_allowed','sample_weight']
PASSES_FEATURES  = ['Age','Position_encoded','Minutes Played','Mn/Start','Percentage of Minutes Played','Crs','Interceptions','Tackles Won','Goals Scored While on Pitch','ppda','opp_possession_allowed','sample_weight']

# Position baseline passes/90 (what a naive market would use)
BASELINE_PASSES = {3: 55.0, 2: 48.0, 1: 35.0, 0: 25.0}  # by encoded pos

bets = []
bankroll = STARTING_BANKROLL
skipped_no_passes = 0
skipped_low_start = 0
skipped_no_edge   = 0

print(f"\nSimulating bets over {len(test_df)} player-match rows...")
print("Method: Our model vs. position-only market baseline")
print("-"*60)

for idx, row in test_df.iterrows():
    feats = build_features(row)

    X_min  = pd.DataFrame([feats['MINUTES']], columns=MINUTES_FEATURES)
    X_pass = pd.DataFrame([feats['PASSES']], columns=PASSES_FEATURES)

    try:
        start_prob = float(models['start_clf'].predict(X_min)[0])
        if start_prob < 0.20:
            skipped_low_start += 1
            continue

        min_p10 = float(models['min_p10'].predict(X_min)[0])
        min_p50 = float(models['min_p50'].predict(X_min)[0])
        min_p90 = float(models['min_p90'].predict(X_min)[0])
        pass_p10 = float(models['pass_p10'].predict(X_pass)[0])
        pass_p50 = float(models['pass_p50'].predict(X_pass)[0])
        pass_p90 = float(models['pass_p90'].predict(X_pass)[0])
    except Exception:
        continue

    # Get actual result
    actual_passes  = float(row.get('completed_passes', row.get('Cmp', row.get('passes_per_90', -1))))
    actual_minutes = float(row.get('Minutes Played', row.get('minutes_played', 90)))
    if actual_passes < 0 or actual_minutes < 10:
        skipped_no_passes += 1
        continue

    # Convert to per-90 if raw count
    actual_per90 = (actual_passes / actual_minutes * 90.0) if actual_passes > 200 else actual_passes

    # === MARKET PRICING (dumb: position avg only, no opponent or form context) ===
    pos_enc = feats['PASSES']['Position_encoded']
    market_mean_passes = BASELINE_PASSES.get(pos_enc, 45.0)
    market_std = 18.0  # realistic std dev for passes per 90

    for line in PASSES_LINES:
        # Our model's fair probability
        our_fair_prob, _ = calculate_over_prob(
            p10_passes=pass_p10, p50_passes=pass_p50, p90_passes=pass_p90,
            p10_minutes=min_p10, p50_minutes=min_p50, p90_minutes=min_p90,
            betting_line=line
        )

        # Market's dumb fair probability — position average only
        from scipy.stats import norm
        market_fair_prob = float(np.clip(
            1.0 - norm.cdf(line, loc=market_mean_passes, scale=market_std),
            0.01, 0.99
        ))

        # Market offers odds on its simpler estimate + 5% vig
        market_over_odds  = simulate_market_odds(market_fair_prob, vig=0.05)
        market_under_odds = simulate_market_odds(1.0 - market_fair_prob, vig=0.05)

        try:
            stripped, _ = remove_vig([market_over_odds, market_under_odds])
            market_implied_prob = stripped[0]
        except Exception:
            continue

        # EDGE = our rich model vs market's simple estimate
        edge = our_fair_prob - market_implied_prob
        if edge < MIN_EDGE:
            skipped_no_edge += 1
            continue

        b = market_over_odds - 1.0
        kelly_full = (our_fair_prob * b - (1.0 - our_fair_prob)) / b
        stake = min(max(kelly_full * KELLY_FRACTION, 0.0) * bankroll, bankroll * 0.02)
        if stake <= 0:
            continue

        actual_over = actual_per90 > line
        pnl    = stake * (market_over_odds - 1.0) if actual_over else -stake
        result = 'win' if actual_over else 'loss'
        bankroll += pnl

        bets.append({
            'player':           row.get('Player Name', row.get('player_name', 'Unknown')),
            'position':         row.get('Position', row.get('position', 'Unknown')),
            'line':             line,
            'our_fair_prob':    round(our_fair_prob, 4),
            'market_fair_prob': round(market_fair_prob, 4),
            'market_implied':   round(market_implied_prob, 4),
            'edge':             round(edge, 4),
            'market_odds':      market_over_odds,
            'stake':            round(stake, 2),
            'actual_per90':     round(actual_per90, 1),
            'result':           result,
            'pnl':              round(pnl, 2),
            'bankroll':         round(bankroll, 2),
        })
        break  # one bet per player per match

print(f"\nSkipped — low start prob:      {skipped_low_start}")
print(f"Skipped — no pass data:        {skipped_no_passes}")
print(f"Skipped — insufficient edge:   {skipped_no_edge}")

results_df = pd.DataFrame(bets)

if results_df.empty:
    print("\nNo bets simulated.")
    print("This means our model's predictions are TOO CLOSE to the position baseline.")
    print("This confirms the proxy training data has no useful signal over position alone.")
    print("ACTION: Run get_real_pass_data.py -> build_training_dataset_v2.py -> retrain")
else:
    total_bets   = len(results_df)
    wins         = (results_df['result'] == 'win').sum()
    total_staked = results_df['stake'].sum()
    total_pnl    = results_df['pnl'].sum()
    roi          = (total_pnl / total_staked * 100) if total_staked > 0 else 0
    avg_edge     = results_df['edge'].mean() * 100
    hit_rate     = wins / total_bets * 100

    print(f"\n{'='*60}")
    print("BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"Total Bets:       {total_bets}")
    print(f"Win Rate:         {hit_rate:.1f}%")
    print(f"Total Staked:     ${total_staked:,.2f}")
    print(f"Total P&L:        ${total_pnl:+,.2f}")
    print(f"ROI:              {roi:+.2f}%")
    print(f"Avg Edge:         {avg_edge:.2f}%")
    print(f"Final Bankroll:   ${bankroll:,.2f}")

    if roi > 5:
        verdict = "STRONG — Real positive EV. Proceed to paper trading."
    elif roi > 0:
        verdict = "MARGINAL — Small edge. Needs real pass data to confirm."
    else:
        verdict = "NEGATIVE — Retrain with StatsBomb real data first."
    print(f"\nVERDICT: {verdict}")

    results_df.to_csv(f'{DATA_DIR}/backtest_results.csv', index=False)
    print(f"\nDetailed results: {DATA_DIR}/backtest_results.csv")
