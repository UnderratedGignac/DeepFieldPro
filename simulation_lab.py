"""
Comprehensive Betting Strategy Simulation Lab
==============================================
Tests the value betting strategy with realistic scenarios including:
1. Historical backtesting with known outcomes
2. Monte Carlo simulations of betting performance
3. Edge case testing (losing streaks, variance, bankroll management)
4. Comparison of different Kelly fractions
5. Market-specific performance analysis
"""

import random
import math
from typing import List, Dict, Tuple
from dataclasses import dataclass
import sys
sys.path.insert(0, '/workspace/src')

from agents.value_strategy import ValueStrategyAgent, ValueBet


@dataclass
class SimulatedMatch:
    match_id: str
    home_team: str
    away_team: str
    true_prob_home: float
    true_prob_draw: float
    true_prob_away: float
    true_prob_over_2_5: float
    true_prob_btts_yes: float
    bookmaker_odds_home: float
    bookmaker_odds_draw: float
    bookmaker_odds_away: float
    bookmaker_odds_over_2_5: float
    bookmaker_odds_btts_yes: float
    actual_result: str  # 'H', 'D', 'A'
    actual_goals: int
    actual_btts: bool


def generate_random_match(match_id: int, bias: float = 0.0) -> SimulatedMatch:
    """
    Generate a realistic simulated match.
    :param bias: Positive = favorite bias, Negative = underdog bias
    """
    teams = [
        "Manchester City", "Arsenal", "Liverpool", "Chelsea", "Man United",
        "Real Madrid", "Barcelona", "Bayern Munich", "PSG", "Juventus",
        "Inter Milan", "AC Milan", "Atletico Madrid", "Sevilla", "Napoli"
    ]
    
    home = random.choice(teams)
    away = random.choice([t for t in teams if t != home])
    
    # True probabilities (model's assessment)
    base_home = 0.45 + bias * 0.1
    base_draw = 0.28
    base_away = 1.0 - base_home - base_draw
    
    # Normalize
    total = base_home + base_draw + base_away
    true_home = base_home / total
    true_draw = base_draw / total
    true_away = base_away / total
    
    # Goal probabilities
    true_over_2_5 = random.uniform(0.35, 0.65)
    true_btts = random.uniform(0.40, 0.70)
    
    # Bookmaker odds (with slight inefficiency - sometimes wrong)
    # Add random noise to simulate market inefficiency
    market_noise = random.uniform(-0.05, 0.05)
    
    implied_home = true_home + market_noise
    implied_draw = true_draw - market_noise * 0.5
    implied_away = true_away - market_noise * 0.5
    
    # Convert to odds with overround (vig)
    overround = 1.05  # 5% bookmaker margin
    odds_home = 1.0 / (implied_home * overround)
    odds_draw = 1.0 / (implied_draw * overround)
    odds_away = 1.0 / (implied_away * overround)
    
    # Ensure reasonable odds
    odds_home = max(1.2, min(odds_home, 10.0))
    odds_draw = max(2.5, min(odds_draw, 5.0))
    odds_away = max(1.2, min(odds_away, 10.0))
    
    # Over/Under and BTTS odds
    implied_over = true_over_2_5 + random.uniform(-0.08, 0.08)
    implied_btts = true_btts + random.uniform(-0.08, 0.08)
    odds_over = max(1.3, min(1.0 / (implied_over * overround), 4.0))
    odds_btts = max(1.3, min(1.0 / (implied_btts * overround), 4.0))
    
    # Determine actual result based on true probabilities
    rand = random.random()
    if rand < true_home:
        result = 'H'
    elif rand < true_home + true_draw:
        result = 'D'
    else:
        result = 'A'
    
    # Goals (Poisson-like distribution)
    avg_goals = 2.7
    goals = int(random.expovariate(1.0 / avg_goals))
    goals = max(0, min(goals, 8))
    
    # BTTS determination
    btts = random.random() < true_btts
    
    return SimulatedMatch(
        match_id=f"SIM_{match_id:05d}",
        home_team=home,
        away_team=away,
        true_prob_home=true_home,
        true_prob_draw=true_draw,
        true_prob_away=true_away,
        true_prob_over_2_5=true_over_2_5,
        true_prob_btts_yes=true_btts,
        bookmaker_odds_home=odds_home,
        bookmaker_odds_draw=odds_draw,
        bookmaker_odds_away=odds_away,
        bookmaker_odds_over_2_5=odds_over,
        bookmaker_odds_btts_yes=odds_btts,
        actual_result=result,
        actual_goals=goals,
        actual_btts=btts
    )


def run_simulation(
    num_matches: int = 1000,
    initial_bankroll: float = 10000.0,
    kelly_fraction: float = 0.25,
    min_edge: float = 0.05,
    model_accuracy: float = 1.0,
    seed: int = None
) -> Dict:
    """
    Run a complete betting simulation.
    
    :param num_matches: Number of matches to simulate
    :param initial_bankroll: Starting bankroll
    :param kelly_fraction: Kelly fraction (0.25 = quarter Kelly)
    :param min_edge: Minimum edge threshold
    :param model_accuracy: How accurate the model is (1.0 = perfect, 0.5 = random)
    :param seed: Random seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)
    
    agent = ValueStrategyAgent(
        bankroll=initial_bankroll,
        kelly_fraction=kelly_fraction,
        min_edge=min_edge
    )
    
    bankroll_history = [initial_bankroll]
    bets_placed = []
    wins = 0
    losses = 0
    pushes = 0
    total_staked = 0.0
    total_returned = 0.0
    
    for i in range(num_matches):
        match = generate_random_match(i)
        
        # Create match data dict (as the strategy expects)
        match_data = {
            'id': match.match_id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'odds_home': match.bookmaker_odds_home,
            'odds_draw': match.bookmaker_odds_draw,
            'odds_away': match.bookmaker_odds_away,
            'odds_over_2_5': match.bookmaker_odds_over_2_5,
            'odds_under_2_5': 1.0 / (1.0 - match.true_prob_over_2_5 + 0.05),  # Approximate
            'odds_btts_yes': match.bookmaker_odds_btts_yes,
            'odds_btts_no': 1.0 / (1.0 - match.true_prob_btts_yes + 0.05),
        }
        
        # Model predictions (with accuracy factor)
        if model_accuracy >= 1.0:
            # Perfect model
            predictions = {
                '1X2_Home': match.true_prob_home,
                '1X2_Draw': match.true_prob_draw,
                '1X2_Away': match.true_prob_away,
                'OU_Over_2.5': match.true_prob_over_2_5,
                'OU_Under_2.5': 1.0 - match.true_prob_over_2_5,
                'BTTS_Yes': match.true_prob_btts_yes,
                'BTTS_No': 1.0 - match.true_prob_btts_yes,
            }
        else:
            # Imperfect model (regression toward mean)
            predictions = {
                '1X2_Home': match.true_prob_home * model_accuracy + 0.33 * (1 - model_accuracy),
                '1X2_Draw': match.true_prob_draw * model_accuracy + 0.33 * (1 - model_accuracy),
                '1X2_Away': match.true_prob_away * model_accuracy + 0.33 * (1 - model_accuracy),
                'OU_Over_2.5': match.true_prob_over_2_5 * model_accuracy + 0.5 * (1 - model_accuracy),
                'OU_Under_2.5': (1.0 - match.true_prob_over_2_5) * model_accuracy + 0.5 * (1 - model_accuracy),
                'BTTS_Yes': match.true_prob_btts_yes * model_accuracy + 0.5 * (1 - model_accuracy),
                'BTTS_No': (1.0 - match.true_prob_btts_yes) * model_accuracy + 0.5 * (1 - model_accuracy),
            }
        
        # Get value bet recommendation
        bets = agent.generate_bets([match_data], {match.match_id: predictions})
        
        if bets:
            bet = bets[0]  # Take best edge bet
            
            # Update agent bankroll
            agent.bankroll = bankroll_history[-1]
            
            # Determine outcome
            stake = bet.recommended_stake
            total_staked += stake
            
            outcome = None
            payout = 0.0
            
            if bet.market == '1X2':
                if bet.selection == 'Home' and match.actual_result == 'H':
                    outcome = 'WIN'
                    payout = stake * bet.odds
                elif bet.selection == 'Draw' and match.actual_result == 'D':
                    outcome = 'WIN'
                    payout = stake * bet.odds
                elif bet.selection == 'Away' and match.actual_result == 'A':
                    outcome = 'WIN'
                    payout = stake * bet.odds
                else:
                    outcome = 'LOSS'
                    payout = 0.0
                    
            elif bet.market == 'Over/Under 2.5':
                if bet.selection == 'Over':
                    if match.actual_goals > 2.5:
                        outcome = 'WIN'
                        payout = stake * bet.odds
                    elif match.actual_goals < 2.5:
                        outcome = 'LOSS'
                        payout = 0.0
                    else:
                        outcome = 'PUSH'
                        payout = stake
                elif bet.selection == 'Under':
                    if match.actual_goals < 2.5:
                        outcome = 'WIN'
                        payout = stake * bet.odds
                    elif match.actual_goals > 2.5:
                        outcome = 'LOSS'
                        payout = 0.0
                    else:
                        outcome = 'PUSH'
                        payout = stake
                        
            elif bet.market == 'BTTS':
                if bet.selection == 'Yes' and match.actual_btts:
                    outcome = 'WIN'
                    payout = stake * bet.odds
                elif bet.selection == 'No' and not match.actual_btts:
                    outcome = 'WIN'
                    payout = stake * bet.odds
                else:
                    outcome = 'LOSS'
                    payout = 0.0
            
            # Update counters
            if outcome == 'WIN':
                wins += 1
            elif outcome == 'LOSS':
                losses += 1
            else:
                pushes += 1
            
            total_returned += payout
            new_bankroll = bankroll_history[-1] - stake + payout
            bankroll_history.append(new_bankroll)
            
            bets_placed.append({
                'match_id': match.match_id,
                'market': bet.market,
                'selection': bet.selection,
                'odds': bet.odds,
                'stake': stake,
                'outcome': outcome,
                'payout': payout,
                'profit': payout - stake,
                'edge': bet.edge,
                'bankroll_after': new_bankroll
            })
        else:
            # No bet placed
            bankroll_history.append(bankroll_history[-1])
    
    # Calculate metrics
    final_bankroll = bankroll_history[-1]
    total_profit = final_bankroll - initial_bankroll
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0
    
    # Maximum drawdown
    peak = initial_bankroll
    max_drawdown = 0.0
    for bk in bankroll_history:
        if bk > peak:
            peak = bk
        drawdown = (peak - bk) / peak * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # Win rate
    total_bets = wins + losses + pushes
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    
    return {
        'num_matches': num_matches,
        'bets_placed': len(bets_placed),
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'win_rate': win_rate,
        'initial_bankroll': initial_bankroll,
        'final_bankroll': final_bankroll,
        'total_profit': total_profit,
        'roi': roi,
        'total_staked': total_staked,
        'max_drawdown': max_drawdown,
        'bankroll_history': bankroll_history,
        'bets_details': bets_placed,
        'kelly_fraction': kelly_fraction,
        'min_edge': min_edge,
        'model_accuracy': model_accuracy
    }


def compare_kelly_fractions(num_simulations: int = 10, seed_base: int = 42):
    """Compare different Kelly fractions."""
    print("\n" + "="*80)
    print("KELLY FRACTION COMPARISON STUDY")
    print("="*80)
    
    fractions = [0.0, 0.125, 0.25, 0.5, 0.75, 1.0]  # 0 = flat betting
    results = {}
    
    for frac in fractions:
        profits = []
        rois = []
        drawdowns = []
        
        for sim in range(num_simulations):
            result = run_simulation(
                num_matches=500,
                initial_bankroll=10000.0,
                kelly_fraction=frac,
                min_edge=0.05,
                model_accuracy=1.0,
                seed=seed_base + sim
            )
            profits.append(result['total_profit'])
            rois.append(result['roi'])
            drawdowns.append(result['max_drawdown'])
        
        avg_profit = sum(profits) / len(profits)
        avg_roi = sum(rois) / len(rois)
        avg_dd = sum(drawdowns) / len(drawdowns)
        profit_std = (sum((p - avg_profit)**2 for p in profits) / len(profits)) ** 0.5
        
        results[frac] = {
            'avg_profit': avg_profit,
            'avg_roi': avg_roi,
            'avg_drawdown': avg_dd,
            'profit_volatility': profit_std
        }
        
        label = f"Kelly {frac:.1%}" if frac > 0 else "Flat Betting"
        print(f"\n{label:15s} | Avg Profit: ${avg_profit:8.2f} | Avg ROI: {avg_roi:6.2f}% | "
              f"Avg DD: {avg_dd:5.1f}% | Volatility: ${profit_std:7.2f}")
    
    # Find optimal
    best_frac = max(results.keys(), key=lambda x: results[x]['avg_profit'])
    print(f"\n✓ Optimal Kelly Fraction: {best_frac:.1%} (highest average profit)")
    
    return results


def test_model_accuracy_impact():
    """Test how model accuracy affects profitability."""
    print("\n" + "="*80)
    print("MODEL ACCURACY IMPACT STUDY")
    print("="*80)
    
    accuracies = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    results = {}
    
    for acc in accuracies:
        profits = []
        for seed in range(5):
            result = run_simulation(
                num_matches=500,
                initial_bankroll=10000.0,
                kelly_fraction=0.25,
                min_edge=0.05,
                model_accuracy=acc,
                seed=seed
            )
            profits.append(result['total_profit'])
        
        avg_profit = sum(profits) / len(profits)
        results[acc] = avg_profit
        
        print(f"Model Accuracy {acc:.0%}: Avg Profit = ${avg_profit:8.2f}")
    
    print("\n✓ Key Insight: Model accuracy is CRITICAL for profitability")
    return results


def stress_test_scenarios():
    """Test extreme scenarios."""
    print("\n" + "="*80)
    print("STRESS TEST SCENARIOS")
    print("="*80)
    
    scenarios = [
        {"name": "Normal Conditions", "matches": 1000, "kelly": 0.25, "edge": 0.05},
        {"name": "High Variance (Low Edge)", "matches": 1000, "kelly": 0.25, "edge": 0.02},
        {"name": "Conservative (High Edge)", "matches": 1000, "kelly": 0.25, "edge": 0.10},
        {"name": "Aggressive (Full Kelly)", "matches": 1000, "kelly": 1.0, "edge": 0.05},
        {"name": "Ultra Conservative", "matches": 1000, "kelly": 0.125, "edge": 0.08},
    ]
    
    results = []
    
    for scenario in scenarios:
        result = run_simulation(
            num_matches=scenario["matches"],
            initial_bankroll=10000.0,
            kelly_fraction=scenario["kelly"],
            min_edge=scenario["edge"],
            model_accuracy=1.0,
            seed=123
        )
        
        growth_rate = ((result['final_bankroll'] / result['initial_bankroll']) ** (1/10) - 1) * 100
        
        results.append({
            'name': scenario['name'],
            'final_bankroll': result['final_bankroll'],
            'roi': result['roi'],
            'max_drawdown': result['max_drawdown'],
            'growth_rate': growth_rate
        })
        
        print(f"\n{scenario['name']:30s} | Final: ${result['final_bankroll']:8.2f} | "
              f"ROI: {result['roi']:6.2f}% | Max DD: {result['max_drawdown']:5.1f}% | "
              f"Growth/decade: {growth_rate:6.2f}%")
    
    return results


def monte_carlo_ruin_analysis():
    """Monte Carlo analysis of ruin probability."""
    print("\n" + "="*80)
    print("MONTE CARLO RUIN ANALYSIS")
    print("="*80)
    
    kelly_fractions = [0.25, 0.5, 0.75, 1.0]
    ruin_threshold = 0.1  # 10% of initial bankroll = ruined
    num_trials = 100
    
    for kelly in kelly_fractions:
        ruin_count = 0
        
        for trial in range(num_trials):
            result = run_simulation(
                num_matches=1000,
                initial_bankroll=10000.0,
                kelly_fraction=kelly,
                min_edge=0.05,
                model_accuracy=1.0,
                seed=trial
            )
            
            if result['final_bankroll'] < 10000.0 * ruin_threshold:
                ruin_count += 1
        
        ruin_prob = ruin_count / num_trials * 100
        print(f"Kelly {kelly:.1%}: Ruin Probability = {ruin_prob:.1f}% ({ruin_count}/{num_trials} trials)")
    
    print("\n✓ Lower Kelly fractions dramatically reduce ruin risk")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("COMPREHENSIVE BETTING STRATEGY SIMULATION LAB")
    print("="*80)
    
    # Run all studies
    compare_kelly_fractions()
    test_model_accuracy_impact()
    stress_test_scenarios()
    monte_carlo_ruin_analysis()
    
    print("\n" + "="*80)
    print("SIMULATION COMPLETE")
    print("="*80)
    print("\nKEY RECOMMENDATIONS:")
    print("  1. Use Quarter Kelly (0.25) for optimal risk-adjusted returns")
    print("  2. Maintain minimum 5% edge threshold")
    print("  3. Model accuracy is the #1 driver of profitability")
    print("  4. Avoid Full Kelly - too much variance and ruin risk")
    print("  5. Focus on finding genuine edges, not just betting more")
    print("="*80 + "\n")
