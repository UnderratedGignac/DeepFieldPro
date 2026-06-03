# -*- coding: utf-8 -*-
"""
calibration_backtester.py — DeepFieldPro Multi-Market Backtester
=================================================================
Backtests SoT, Passes, and Tackles markets to find best calibrated market.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P  (e.g. Market_P)
- Variables:  ProperCase suffix _V  (e.g. BrierScore_V)
- SQL keywords: UPPERCASE
- Comments: single line, max 1 line
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone


DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
BACKTEST_CSV = os.path.join(DATA_DIR, 'backtest_results.csv')


def load_backtest_data():
    """Load historical backtest results."""
    if not os.path.exists(BACKTEST_CSV):
        print(f"ERROR: Backtest file not found: {BACKTEST_CSV}")
        return None
    return pd.read_csv(BACKTEST_CSV)


def compute_brier_score(predicted_probs, actual_outcomes):
    """Compute Brier Score (mean squared error for probabilities)."""
    predicted_probs = np.array(predicted_probs)
    actual_outcomes = np.array(actual_outcomes)
    return np.mean((predicted_probs - actual_outcomes) ** 2)


def compute_bucket_calibration(predicted_probs, actual_outcomes, buckets):
    """
    Compute calibration by probability bucket.
    Returns dict with sample_size, expected_win_pct, actual_win_pct per bucket.
    """
    results = {}
    for bucket_low, bucket_high in buckets:
        mask = (predicted_probs > bucket_low) & (predicted_probs <= bucket_high)
        bucket_probs = predicted_probs[mask]
        bucket_outcomes = actual_outcomes[mask]
        
        n = len(bucket_outcomes)
        if n == 0:
            results[f'({bucket_low},{bucket_high}]'] = {
                'sample_size': 0,
                'expected_win_pct': None,
                'actual_win_pct': None,
                'gap_pp': None
            }
        else:
            expected_win = np.mean(bucket_probs) * 100
            actual_win = np.mean(bucket_outcomes) * 100
            gap = abs(expected_win - actual_win)
            results[f'({bucket_low},{bucket_high}]'] = {
                'sample_size': n,
                'expected_win_pct': expected_win,
                'actual_win_pct': actual_win,
                'gap_pp': gap
            }
    return results


def backtest_market(df, Market_P, threshold=None):
    """
    Backtest a specific market.
    
    Market_P values:
    - 'sot_over_0.5'
    - 'passes_over_X' (threshold required)
    - 'tackles_over_X' (threshold required)
    """
    print(f"\n{'='*60}")
    print(f"BACKTEST: {Market_P}" + (f" threshold={threshold}" if threshold else ""))
    print(f"{'='*60}")
    
    # Filter relevant rows
    if Market_P == 'sot_over_0.5':
        prob_col = 'pred_prob_sot'
        outcome_col = 'actual_sot_over_0_5'
    elif Market_P.startswith('passes_over'):
        prob_col = 'pred_prob_passes'
        outcome_col = f'actual_passes_over_{threshold}'
    elif Market_P.startswith('tackles_over'):
        prob_col = 'pred_prob_tackles'
        outcome_col = f'actual_tackles_over_{threshold}'
    else:
        print(f"ERROR: Unknown market {Market_P}")
        return None
    
    if prob_col not in df.columns or outcome_col not in df.columns:
        print(f"SKIP: Required columns not in dataset")
        return None
    
    valid_df = df.dropna(subset=[prob_col, outcome_col])
    n_valid = len(valid_df)
    
    if n_valid == 0:
        print(f"SKIP: No valid predictions for this market")
        return None
    
    predicted_probs = valid_df[prob_col].values
    actual_outcomes = valid_df[outcome_col].values
    
    # Global Brier Score
    BrierScore_V = compute_brier_score(predicted_probs, actual_outcomes)
    
    # Bucket calibration
    Buckets_P = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
    BucketCal_V = compute_bucket_calibration(predicted_probs, actual_outcomes, Buckets_P)
    
    # Find max calibration gap
    MaxGap_V = 0.0
    BestBucket_V = None
    for bucket_name, stats in BucketCal_V.items():
        if stats['gap_pp'] is not None and stats['gap_pp'] > MaxGap_V:
            MaxGap_V = stats['gap_pp']
            BestBucket_V = bucket_name
    
    # Verdict
    if BrierScore_V < 0.15 and MaxGap_V < 10.0:
        Verdict_V = 'PAPER_TRADE_READY'
    elif BrierScore_V < 0.18 and MaxGap_V < 20.0:
        Verdict_V = 'NEEDS_CALIBRATION'
    else:
        Verdict_V = 'FAIL'
    
    print(f"\nResults:")
    print(f"  Valid Predictions: {n_valid}")
    print(f"  Brier Score: {BrierScore_V:.4f} (target: <0.15)")
    print(f"  Max Calibration Gap: {MaxGap_V:.1f}pp (target: <10pp)")
    print(f"  Best Bucket: {BestBucket_V}")
    print(f"  Verdict: {Verdict_V}")
    
    print(f"\nBucket Breakdown:")
    print(f"  {'Bucket':<15} | {'Samples':>8} | {'Expected%':>10} | {'Actual%':>9} | {'Gap(pp)':>8}")
    print(f"  {'-'*15}-|-{'-'*8}-|-{'-'*10}-|-{'-'*9}-|-{'-'*8}")
    for bucket_name, stats in BucketCal_V.items():
        if stats['sample_size'] > 0:
            print(f"  {bucket_name:<15} | {stats['sample_size']:>8} | {stats['expected_win_pct']:>9.1f}% | {stats['actual_win_pct']:>8.1f}% | {stats['gap_pp']:>7.1f}")
        else:
            print(f"  {bucket_name:<15} | {stats['sample_size']:>8} | {'N/A':>10} | {'N/A':>9} | {'N/A':>8}")
    
    return {
        'market': Market_P,
        'threshold': threshold,
        'n_valid': n_valid,
        'brier_score': BrierScore_V,
        'max_gap_pp': MaxGap_V,
        'best_bucket': BestBucket_V,
        'verdict': Verdict_V,
        'bucket_calibrations': BucketCal_V
    }


def run_full_backtest():
    """Run backtest across all markets and thresholds."""
    print("="*70)
    print("DeepFieldPro Multi-Market Calibration Backtest")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("="*70)
    
    df = load_backtest_data()
    if df is None:
        print("\nGenerating synthetic backtest data for demo...")
        df = generate_synthetic_backtest_data()
    
    results = []
    
    # SoT market
    result = backtest_market(df, 'sot_over_0.5')
    if result:
        results.append(result)
    
    # Passes markets
    for threshold in [30.5, 40.5, 50.5]:
        result = backtest_market(df, f'passes_over_{threshold}', threshold=threshold)
        if result:
            results.append(result)
    
    # Tackles markets
    for threshold in [0.5, 1.5, 2.5]:
        result = backtest_market(df, f'tackles_over_{threshold}', threshold=threshold)
        if result:
            results.append(result)
    
    # Print comparison table
    print("\n" + "="*70)
    print("MARKET COMPARISON TABLE")
    print("="*70)
    print(f"{'Market':<25} | {'Brier':>7} | {'Max Gap':>9} | {'Best Bucket':<12} | {'Verdict':<18}")
    print(f"{'-'*25}-|-{'-'*7}-|-{'-'*9}-|-{'-'*12}-|-{'-'*18}")
    
    paper_trade_ready = []
    for r in results:
        market_label = r['market']
        if r['threshold']:
            market_label += f" ({r['threshold']})"
        verdict_symbol = "✓" if r['verdict'] == 'PAPER_TRADE_READY' else " "
        print(f"{verdict_symbol} {market_label:<24} | {r['brier_score']:>7.4f} | {r['max_gap_pp']:>8.1f}pp | {r['best_bucket']:<12} | {r['verdict']:<18}")
        
        if r['verdict'] == 'PAPER_TRADE_READY':
            paper_trade_ready.append(r['market'])
    
    print("\n" + "="*70)
    if paper_trade_ready:
        print(f"PAPER TRADE RECOMMENDATION: {paper_trade_ready[0]}")
        print(f"Reason: Brier < 0.15 AND max calibration gap < 10pp")
    else:
        print("NO MARKET READY FOR PAPER TRADING")
        print("Recommendation: Continue model refinement or apply Platt scaling")
    print("="*70)
    
    return results


def generate_synthetic_backtest_data():
    """Generate synthetic backtest data for demonstration."""
    np.random.seed(42)
    n_samples = 829
    
    # Simulate poorly calibrated SoT (like club model on international)
    pred_sot = np.random.beta(2, 2, n_samples)  # 0.2-0.8 range
    actual_sot = np.random.binomial(1, pred_sot * 0.5, n_samples)  # Overconfident
    
    # Simulate better calibrated passes
    pred_passes = np.random.uniform(0.3, 0.7, n_samples)
    actual_passes = np.random.binomial(1, pred_passes * 0.95, n_samples)  # Slight overconfidence
    
    # Simulate well calibrated tackles
    pred_tackles = np.random.uniform(0.2, 0.6, n_samples)
    actual_tackles = np.random.binomial(1, pred_tackles * 1.02, n_samples)  # Nearly perfect
    
    df = pd.DataFrame({
        'pred_prob_sot': pred_sot,
        'actual_sot_over_0_5': actual_sot,
        'pred_prob_passes': pred_passes,
        'actual_passes_over_30.5': actual_passes,
        'actual_passes_over_40.5': actual_passes,
        'actual_passes_over_50.5': actual_passes,
        'pred_prob_tackles': pred_tackles,
        'actual_tackles_over_0.5': actual_tackles,
        'actual_tackles_over_1.5': actual_tackles,
        'actual_tackles_over_2.5': actual_tackles
    })
    
    return df


if __name__ == "__main__":
    results = run_full_backtest()
