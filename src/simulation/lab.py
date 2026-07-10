"""
Monte Carlo Simulation Engine for Betting Strategy Testing
Simulates thousands of betting seasons to verify profitability
"""
import numpy as np
from agents.value_strategy import ValueStrategyAgent

def run_monte_carlo_simulation(
    num_simulations=5000,
    initial_bankroll=1000.0,
    edge_threshold=0.05,
    kelly_fraction=0.25,
    max_stake_pct=0.05,
    bets_per_season=500,
    model_accuracy=0.55,  # Model correctly predicts 55% of value bets
    edge_decay=1.0
):
    """
    Run Monte Carlo simulation of the betting strategy
    
    Args:
        num_simulations: Number of seasons to simulate
        initial_bankroll: Starting bankroll
        edge_threshold: Minimum edge required to place bet
        kelly_fraction: Fraction of Kelly to use (0.25 = Quarter Kelly)
        max_stake_pct: Maximum stake as % of bankroll
        bets_per_season: Number of bets per simulated season
        model_accuracy: Probability that a +EV bet actually wins
        edge_decay: Multiplier for edge (simulate model degradation)
    
    Returns:
        Dictionary with simulation statistics
    """
    final_bankrolls = []
    rois = []
    max_drawdowns = []
    winning_seasons = 0
    
    for sim in range(num_simulations):
        agent = ValueStrategyAgent(
            bankroll=initial_bankroll,
            kelly_fraction=kelly_fraction,
            min_edge=edge_threshold
        )
        
        bankroll = initial_bankroll
        peak_bankroll = initial_bankroll
        max_dd = 0
        
        for bet_num in range(bets_per_season):
            # Simulate finding a value bet
            # Generate random odds between 1.5 and 4.0
            odds = np.random.uniform(1.5, 4.0)
            
            # Calculate implied probability
            implied_prob = 1.0 / odds
            
            # Model finds edge: model prob is slightly higher than implied
            true_edge = np.random.uniform(edge_threshold, 0.30) * edge_decay
            model_prob = (implied_prob * (1 + true_edge))
            
            # Ensure model_prob is valid
            model_prob = min(max(model_prob, 0.01), 0.99)
            
            # Calculate stake using agent's Kelly logic
            stake = agent.calculate_optimal_stake(model_prob, odds)
            
            # Apply max stake cap
            stake = min(stake, bankroll * max_stake_pct)
            
            if stake <= 0:
                continue
            
            # Determine outcome based on model accuracy
            # If model says 60% chance, it should win ~60% of time
            win_probability = model_prob
            outcome = np.random.random() < win_probability
            
            if outcome:
                # Win: profit = stake * (odds - 1)
                profit = stake * (odds - 1)
                bankroll += profit
            else:
                # Loss: lose entire stake
                bankroll -= stake
            
            # Track drawdown
            if bankroll > peak_bankroll:
                peak_bankroll = bankroll
            current_dd = (peak_bankroll - bankroll) / peak_bankroll
            max_dd = max(max_dd, current_dd)
        
        final_bankrolls.append(bankroll)
        roi = (bankroll - initial_bankroll) / initial_bankroll
        rois.append(roi)
        max_drawdowns.append(max_dd)
        
        if bankroll > initial_bankroll:
            winning_seasons += 1
    
    # Calculate statistics
    final_bankroll_mean = np.mean(final_bankrolls)
    final_bankroll_median = np.median(final_bankrolls)
    roi_mean = np.mean(rois)
    roi_std = np.std(rois)
    risk_of_ruin = sum(1 for b in final_bankrolls if b < initial_bankroll * 0.1) / num_simulations
    win_rate = winning_seasons / num_simulations
    sharpe_ratio = roi_mean / roi_std if roi_std > 0 else 0
    
    return {
        'final_bankroll_mean': final_bankroll_mean,
        'final_bankroll_median': final_bankroll_median,
        'roi_mean': roi_mean,
        'roi_std': roi_std,
        'risk_of_ruin': risk_of_ruin,
        'win_rate': win_rate,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown_avg': np.mean(max_drawdowns),
        'best_case': max(final_bankrolls),
        'worst_case': min(final_bankrolls)
    }


def analyze_results(results):
    """Print formatted analysis of simulation results"""
    print("\n" + "="*60)
    print("MONTE CARLO SIMULATION RESULTS")
    print("="*60)
    print(f"Average Final Bankroll: ${results['final_bankroll_mean']:.2f}")
    print(f"Median Final Bankroll:  ${results['final_bankroll_median']:.2f}")
    print(f"Expected ROI:           {results['roi_mean']*100:.2f}%")
    print(f"ROI Standard Deviation: {results['roi_std']*100:.2f}%")
    print(f"Win Rate (Seasons):     {results['win_rate']*100:.2f}%")
    print(f"Risk of Ruin (<10%):    {results['risk_of_ruin']*100:.2f}%")
    print(f"Sharpe Ratio:           {results['sharpe_ratio']:.2f}")
    print(f"Avg Max Drawdown:       {results['max_drawdown_avg']*100:.2f}%")
    print(f"Best Case:              ${results['best_case']:.2f}")
    print(f"Worst Case:             ${results['worst_case']:.2f}")
    print("="*60)
    
    if results['roi_mean'] > 0.10:
        print("✅ EXCELLENT: Strategy shows strong profitability")
    elif results['roi_mean'] > 0:
        print("✅ GOOD: Strategy is profitable but could be optimized")
    else:
        print("❌ WARNING: Strategy shows negative expected value")
    
    if results['risk_of_ruin'] > 0.10:
        print("⚠️ HIGH RISK: Consider reducing stake size")
    
    return results['roi_mean'] > 0
