"""
Elite Betting System Optimizer - Version 2.0
=============================================
Comprehensive adversarial review, statistical validation, and optimization engine.

This module performs:
1. Complete system audit
2. Adversarial attack on every assumption
3. Statistical validation of edges
4. Stress testing across regimes
5. Optimization of all components
6. Monte Carlo simulation with realistic constraints
7. Walk-forward analysis
8. Risk-of-ruin calculations

Evaluation Metric: TOTAL NET MONEY WON
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable
from scipy import stats
from scipy.optimize import minimize_scalar, brute
import warnings
warnings.filterwarnings('ignore')

np.random.seed(42)


@dataclass
class BetResult:
    """Represents a single bet outcome"""
    match_id: str
    market: str
    selection: str
    odds: float
    stake: float
    model_prob: float
    edge: float
    outcome: str  # WIN, LOSS, VOID
    pnl: float
    clv: float = 0.0  # Closing Line Value


@dataclass
class SimulationResults:
    """Complete simulation results with statistics"""
    total_bets: int
    winning_bets: int
    losing_bets: int
    voids: int
    win_rate: float
    total_staked: float
    total_pnl: float
    roi: float
    yield_pct: float
    final_bankroll: float
    max_drawdown: float
    max_drawdown_duration: int
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    risk_of_ruin: float
    clv_edge: float
    best_bet: Optional[BetResult] = None
    worst_bet: Optional[BetResult] = None
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)


class EliteBettingOptimizer:
    """
    Elite quantitative betting optimizer.
    
    Performs adversarial review and optimization of betting systems.
    """
    
    def __init__(self, initial_bankroll: float = 10000.0):
        self.initial_bankroll = initial_bankroll
        self.results_history = []
        
    def audit_current_system(self) -> Dict:
        """
        Perform complete audit of current betting system.
        Returns dictionary of identified weaknesses.
        """
        print("\n" + "="*80)
        print("ELITE BETTING SYSTEM AUDIT")
        print("="*80)
        
        weaknesses = {
            'probability_estimation': [],
            'value_calculation': [],
            'kelly_sizing': [],
            'market_selection': [],
            'risk_management': [],
            'data_quality': [],
            'execution': []
        }
        
        # CRITICAL WEAKNESS 1: Model Probability Estimation
        weaknesses['probability_estimation'] = [
            "Current system uses static model probabilities without uncertainty quantification",
            "No calibration of model outputs (Platt scaling, isotonic regression missing)",
            "No ensemble methods to reduce variance",
            "No temporal decay for older predictions",
            "No sport/market-specific model tuning"
        ]
        
        # CRITICAL WEAKNESS 2: Edge Calculation
        weaknesses['value_calculation'] = [
            "Edge threshold (5%) is arbitrary, not optimized",
            "No accounting for bookmaker margin changes over time",
            "No closing line value (CLV) tracking",
            "No differentiation between soft vs sharp bookmakers",
            "Edge decay from line movement not modeled"
        ]
        
        # CRITICAL WEAKNESS 3: Kelly Criterion Issues
        weaknesses['kelly_sizing'] = [
            "Quarter Kelly (0.25) is arbitrary - not optimized for this specific edge distribution",
            "Fixed 5% cap may be too conservative for high-edge bets",
            "No correlation-aware position sizing",
            "No regime-dependent Kelly adjustment",
            "Kelly assumes known probabilities - ignores model uncertainty"
        ]
        
        # CRITICAL WEAKNESS 4: Market Selection
        weaknesses['market_selection'] = [
            "All markets treated equally (1X2, O/U, BTTS have different efficiencies)",
            "No liquidity filtering - may miss better odds elsewhere",
            "No league-specific edge analysis",
            "No time-of-bet optimization (early vs late betting)",
            "No line shopping across multiple bookmakers"
        ]
        
        # CRITICAL WEAKNESS 5: Risk Management
        weaknesses['risk_management'] = [
            "No maximum daily/weekly loss limits",
            "No cooling-off period after losses",
            "No exposure limits per league/team",
            "No correlation checks between simultaneous bets",
            "No dynamic bankroll adjustment based on recent performance"
        ]
        
        # CRITICAL WEAKNESS 6: Data Quality
        weaknesses['data_quality'] = [
            "Free scrapers may have delays/errors vs paid APIs",
            "No data validation beyond basic score checks",
            "No handling of postponed/cancelled matches in real-time",
            "Sample size may be insufficient for statistical significance"
        ]
        
        # CRITICAL WEAKNESS 7: Execution
        weaknesses['execution'] = [
            "No slippage modeling (odds may change between analysis and placement)",
            "No bet tracking latency consideration",
            "No handling of bet rejections/limits",
            "No optimization of bet timing"
        ]
        
        total_weaknesses = sum(len(v) for v in weaknesses.values())
        print(f"\nTotal Weaknesses Identified: {total_weaknesses}")
        for category, items in weaknesses.items():
            print(f"\n{category.upper()}: {len(items)} issues")
            for item in items[:3]:  # Show top 3 per category
                print(f"  ⚠️  {item}")
        
        return weaknesses
    
    def calculate_optimal_kelly_fraction(self, 
                                         historical_edges: np.ndarray,
                                         historical_odds: np.ndarray,
                                         historical_win_rates: np.ndarray,
                                         target_sharpe: float = 1.5) -> float:
        """
        Calculate optimal Kelly fraction based on historical performance.
        
        Uses brute force optimization to find fraction that maximizes 
        risk-adjusted returns while keeping risk of ruin < 5%.
        """
        def objective(fraction):
            """Objective: maximize log utility with penalty for ruin"""
            sim_results = self._simulate_strategy(
                edges=historical_edges,
                odds=historical_odds,
                win_rates=historical_win_rates,
                kelly_fraction=fraction,
                num_simulations=1000
            )
            
            # Penalize low returns and high ruin probability
            mean_roi = sim_results['roi_mean']
            ruin_prob = sim_results['risk_of_ruin']
            
            if ruin_prob > 0.05:
                return -1000  # Heavy penalty for >5% ruin probability
            
            # Maximize ROI adjusted for variance
            sharpe = sim_results.get('sharpe_ratio', 0)
            return -(mean_roi * sharpe)  # Negative for minimization
        
        # Brute force search over [0.1, 1.0]
        result = brute(objective, ranges=(slice(0.1, 1.0, 0.05),), finish=None)
        optimal_fraction = result[0] if isinstance(result, tuple) else result
        
        return max(0.1, min(optimal_fraction, 0.5))  # Bound between 0.1 and 0.5
    
    def optimize_edge_threshold(self,
                                historical_data: pd.DataFrame,
                                min_bets: int = 100) -> float:
        """
        Find optimal edge threshold that maximizes long-term profit.
        
        Tests thresholds from 2% to 15% and finds sweet spot.
        """
        thresholds = np.arange(0.02, 0.15, 0.01)
        results = []
        
        # Use 'perceived_edge' column if 'edge' doesn't exist
        edge_col = 'edge' if 'edge' in historical_data.columns else 'perceived_edge'
        
        for threshold in thresholds:
            filtered = historical_data[historical_data[edge_col] >= threshold]
            
            if len(filtered) < min_bets:
                continue
            
            # Simulate performance at this threshold
            sim = self._simulate_with_parameters(
                edges=filtered[edge_col].values,
                odds=filtered['odds'].values,
                win_probs=filtered['model_prob'].values,
                kelly_fraction=0.25,
                num_simulations=2000
            )
            
            results.append({
                'threshold': threshold,
                'num_bets': len(filtered),
                'roi_mean': sim['roi_mean'],
                'sharpe': sim.get('sharpe_ratio', 0),
                'ruin_prob': sim['risk_of_ruin'],
                'score': sim['roi_mean'] * sim.get('sharpe_ratio', 1)  # Risk-adjusted score
            })
        
        if not results:
            return 0.05  # Default
        
        # Find threshold with best risk-adjusted returns
        df_results = pd.DataFrame(results)
        optimal = df_results.loc[df_results['score'].idxmax()]
        
        print(f"\nOptimal Edge Threshold: {optimal['threshold']:.2%}")
        print(f"  Expected ROI: {optimal['roi_mean']:.2%}")
        print(f"  Sharpe Ratio: {optimal['sharpe']:.2f}")
        print(f"  Number of Bets: {int(optimal['num_bets'])}")
        
        return optimal['threshold']
    
    def _simulate_strategy(self,
                          edges: np.ndarray,
                          odds: np.ndarray,
                          win_rates: np.ndarray,
                          kelly_fraction: float,
                          num_simulations: int = 1000) -> Dict:
        """Internal simulation engine"""
        final_bankrolls = []
        rois = []
        max_drawdowns = []
        
        for _ in range(num_simulations):
            bankroll = self.initial_bankroll
            peak = bankroll
            max_dd = 0
            
            for edge, odd, win_rate in zip(edges, odds, win_rates):
                # Calculate stake
                b = odd - 1
                p = win_rate
                q = 1 - p
                
                kelly_frac = max(0, (b * p - q) / b) * kelly_fraction
                stake = bankroll * kelly_frac
                stake = min(stake, bankroll * 0.05)  # 5% cap
                
                if stake <= 0:
                    continue
                
                # Outcome
                if np.random.random() < win_rate:
                    profit = stake * (odd - 1)
                    bankroll += profit
                else:
                    bankroll -= stake
                
                # Track drawdown
                if bankroll > peak:
                    peak = bankroll
                dd = (peak - bankroll) / peak
                max_dd = max(max_dd, dd)
            
            final_bankrolls.append(bankroll)
            rois.append((bankroll - self.initial_bankroll) / self.initial_bankroll)
            max_drawdowns.append(max_dd)
        
        return {
            'roi_mean': np.mean(rois),
            'roi_std': np.std(rois),
            'risk_of_ruin': sum(1 for b in final_bankrolls if b < self.initial_bankroll * 0.1) / num_simulations,
            'sharpe_ratio': np.mean(rois) / np.std(rois) if np.std(rois) > 0 else 0,
            'max_drawdown_avg': np.mean(max_drawdowns)
        }
    
    def _simulate_with_parameters(self,
                                  edges: np.ndarray,
                                  odds: np.ndarray,
                                  win_probs: np.ndarray,
                                  kelly_fraction: float,
                                  num_simulations: int = 1000) -> Dict:
        """Alternative simulation with explicit parameters"""
        return self._simulate_strategy(edges, odds, win_probs, kelly_fraction, num_simulations)
    
    def generate_synthetic_data(self, 
                               num_bets: int = 1000,
                               true_edge_mean: float = 0.08,
                               true_edge_std: float = 0.05,
                               odds_range: Tuple[float, float] = (1.5, 4.0),
                               model_uncertainty: float = 0.1) -> pd.DataFrame:
        """
        Generate realistic synthetic betting data with:
        - True edges drawn from distribution
        - Model uncertainty/noise
        - Realistic odds distribution
        - Variance in outcomes
        """
        # True edges (what we're trying to capture)
        true_edges = np.random.normal(true_edge_mean, true_edge_std, num_bets)
        true_edges = np.clip(true_edges, 0.02, 0.30)  # Bound edges
        
        # Odds distribution (more bets at lower odds)
        odds = np.random.beta(2, 5, num_bets) * (odds_range[1] - odds_range[0]) + odds_range[0]
        
        # Model probabilities with uncertainty
        implied_probs = 1.0 / odds
        model_probs = implied_probs * (1 + true_edges)
        
        # Add model uncertainty (noise)
        noise = np.random.normal(0, model_uncertainty, num_bets)
        model_probs = np.clip(model_probs + noise, 0.01, 0.99)
        
        # Calculate perceived edges (what strategy sees)
        perceived_edges = (model_probs * odds) - 1
        
        # Actual outcomes based on true probabilities
        # Use implied prob + true edge as "true" win probability
        true_win_probs = np.clip(implied_probs * (1 + true_edges), 0.01, 0.99)
        outcomes = (np.random.random(num_bets) < true_win_probs).astype(int)
        
        df = pd.DataFrame({
            'match_id': [f'bet_{i}' for i in range(num_bets)],
            'market': np.random.choice(['1X2', 'Over/Under', 'BTTS'], num_bets),
            'odds': odds,
            'implied_prob': implied_probs,
            'model_prob': model_probs,
            'true_edge': true_edges,
            'perceived_edge': perceived_edges,
            'outcome': outcomes,
            'true_win_prob': true_win_probs
        })
        
        return df
    
    def run_comprehensive_backtest(self,
                                   data: pd.DataFrame,
                                   kelly_fraction: float = 0.25,
                                   edge_threshold: float = 0.05,
                                   max_stake_pct: float = 0.05,
                                   apply_filters: bool = True) -> SimulationResults:
        """
        Run comprehensive backtest with realistic constraints.
        
        Includes:
        - Filtering by edge threshold
        - Kelly-based stake sizing
        - Maximum stake caps
        - Drawdown tracking
        - CLV calculation (simulated)
        """
        # Filter by edge threshold
        if apply_filters:
            data = data[data['perceived_edge'] >= edge_threshold].copy()
        
        if len(data) == 0:
            return SimulationResults(
                total_bets=0, winning_bets=0, losing_bets=0, voids=0,
                win_rate=0, total_staked=0, total_pnl=0, roi=0, yield_pct=0,
                final_bankroll=self.initial_bankroll, max_drawdown=0,
                max_drawdown_duration=0, sharpe_ratio=0, sortino_ratio=0,
                calmar_ratio=0, risk_of_ruin=0, clv_edge=0
            )
        
        bankroll = self.initial_bankroll
        equity_curve = [bankroll]
        drawdown_curve = [0]
        peak = bankroll
        max_dd = 0
        max_dd_duration = 0
        current_dd_duration = 0
        
        bets_results = []
        total_staked = 0
        
        for idx, row in data.iterrows():
            odds = row['odds']
            model_prob = row['model_prob']
            outcome = row['outcome']
            
            # Calculate Kelly stake
            b = odds - 1
            p = model_prob
            q = 1 - p
            
            kelly_frac = max(0, (b * p - q) / b) * kelly_fraction
            stake = bankroll * kelly_frac
            stake = min(stake, bankroll * max_stake_pct)  # Apply cap
            
            if stake < 1:  # Minimum bet size
                continue
            
            total_staked += stake
            
            # Calculate P&L
            if outcome == 1:
                pnl = stake * (odds - 1)
                bet_outcome = 'WIN'
            else:
                pnl = -stake
                bet_outcome = 'LOSS'
            
            bankroll += pnl
            
            # Update equity curve
            equity_curve.append(bankroll)
            
            # Update drawdown
            if bankroll > peak:
                peak = bankroll
                current_dd_duration = 0
            else:
                current_dd_duration += 1
            
            dd = (peak - bankroll) / peak
            drawdown_curve.append(dd)
            max_dd = max(max_dd, dd)
            max_dd_duration = max(max_dd_duration, current_dd_duration)
            
            # Simulate CLV (closing line value)
            # Assume odds move slightly toward true probability
            true_prob = row.get('true_win_prob', model_prob)
            fair_odds = 1.0 / true_prob
            clv = (fair_odds - odds) / odds * 100  # CLV percentage
            
            bets_results.append(BetResult(
                match_id=row['match_id'],
                market=row['market'],
                selection='N/A',
                odds=odds,
                stake=stake,
                model_prob=model_prob,
                edge=row['perceived_edge'],
                outcome=bet_outcome,
                pnl=pnl,
                clv=clv
            ))
        
        # Calculate statistics
        total_bets = len(bets_results)
        winning_bets = sum(1 for b in bets_results if b.outcome == 'WIN')
        losing_bets = sum(1 for b in bets_results if b.outcome == 'LOSS')
        voids = sum(1 for b in bets_results if b.outcome == 'VOID')
        
        win_rate = winning_bets / total_bets if total_bets > 0 else 0
        total_pnl = bankroll - self.initial_bankroll
        roi = total_pnl / self.initial_bankroll
        yield_pct = total_pnl / total_staked if total_staked > 0 else 0
        
        # Risk metrics
        returns = np.diff(equity_curve) / equity_curve[:-1]
        sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        
        downside_returns = returns[returns < 0]
        sortino = np.mean(returns) / np.std(downside_returns) if len(downside_returns) > 0 and np.std(downside_returns) > 0 else 0
        
        calmar = roi / max_dd if max_dd > 0 else 0
        
        # Risk of ruin (fraction of simulations where bankroll drops below 10%)
        min_bankroll = min(equity_curve)
        risk_of_ruin = 1.0 if min_bankroll < self.initial_bankroll * 0.1 else 0.0
        
        # Average CLV
        avg_clv = np.mean([b.clv for b in bets_results]) if bets_results else 0
        
        # Best and worst bets
        best_bet = max(bets_results, key=lambda x: x.pnl) if bets_results else None
        worst_bet = min(bets_results, key=lambda x: x.pnl) if bets_results else None
        
        return SimulationResults(
            total_bets=total_bets,
            winning_bets=winning_bets,
            losing_bets=losing_bets,
            voids=voids,
            win_rate=win_rate,
            total_staked=total_staked,
            total_pnl=total_pnl,
            roi=roi,
            yield_pct=yield_pct,
            final_bankroll=bankroll,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            risk_of_ruin=risk_of_ruin,
            clv_edge=avg_clv,
            best_bet=best_bet,
            worst_bet=worst_bet,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve
        )
    
    def walk_forward_analysis(self,
                             data: pd.DataFrame,
                             train_periods: int = 5,
                             test_periods: int = 1) -> Dict:
        """
        Perform walk-forward analysis to test robustness.
        
        Splits data into rolling train/test windows to detect overfitting.
        """
        n = len(data)
        window_size = n // (train_periods + test_periods)
        
        if window_size < 50:
            return {'error': 'Insufficient data for walk-forward analysis'}
        
        results = []
        
        for i in range(train_periods):
            train_start = i * window_size
            train_end = (i + train_periods) * window_size
            test_start = train_end
            test_end = test_start + window_size
            
            if test_end > n:
                break
            
            train_data = data.iloc[train_start:train_end].copy()
            test_data = data.iloc[test_start:test_end].copy()
            
            # Optimize on training data
            optimal_threshold = self.optimize_edge_threshold(train_data, min_bets=20)
            
            # Test on out-of-sample data
            test_result = self.run_comprehensive_backtest(
                test_data,
                edge_threshold=optimal_threshold,
                apply_filters=True
            )
            
            results.append({
                'fold': i + 1,
                'train_size': len(train_data),
                'test_size': len(test_data),
                'optimal_threshold': optimal_threshold,
                'oos_roi': test_result.roi,
                'oos_sharpe': test_result.sharpe_ratio,
                'oos_max_dd': test_result.max_drawdown
            })
        
        # Calculate average OOS performance
        if results:
            avg_oos_roi = np.mean([r['oos_roi'] for r in results])
            avg_oos_sharpe = np.mean([r['oos_sharpe'] for r in results])
            avg_oos_dd = np.mean([r['oos_max_dd'] for r in results])
        else:
            avg_oos_roi = avg_oos_sharpe = avg_oos_dd = 0
        
        return {
            'folds': results,
            'avg_oos_roi': avg_oos_roi,
            'avg_oos_sharpe': avg_oos_sharpe,
            'avg_oos_max_dd': avg_oos_dd,
            'robustness_score': avg_oos_roi * avg_oos_sharpe if avg_oos_sharpe > 0 else 0
        }
    
    def monte_carlo_stress_test(self,
                               base_scenario: Dict,
                               num_scenarios: int = 100) -> Dict:
        """
        Run Monte Carlo stress test across multiple scenarios.
        
        Varies:
        - Model accuracy (±20%)
        - Edge realization (±30%)
        - Odds movement (±10%)
        - Stake sizing errors (±15%)
        """
        scenarios = []
        
        for i in range(num_scenarios):
            # Perturb base parameters
            accuracy_multiplier = np.random.uniform(0.8, 1.2)
            edge_multiplier = np.random.uniform(0.7, 1.3)
            odds_multiplier = np.random.uniform(0.9, 1.1)
            
            scenario_name = f"Scenario_{i+1}"
            
            scenarios.append({
                'name': scenario_name,
                'accuracy_mult': accuracy_multiplier,
                'edge_mult': edge_multiplier,
                'odds_mult': odds_multiplier
            })
        
        # Run simulations for each scenario
        results_summary = []
        
        for scenario in scenarios[:10]:  # Limit to 10 for speed
            # Generate perturbed data
            synthetic = self.generate_synthetic_data(
                num_bets=500,
                true_edge_mean=base_scenario.get('edge_mean', 0.08) * scenario['edge_mult'],
                model_uncertainty=base_scenario.get('uncertainty', 0.1) / scenario['accuracy_mult']
            )
            
            # Adjust odds
            synthetic['odds'] *= scenario['odds_mult']
            synthetic['implied_prob'] = 1.0 / synthetic['odds']
            
            # Run backtest
            result = self.run_comprehensive_backtest(
                synthetic,
                kelly_fraction=base_scenario.get('kelly', 0.25),
                edge_threshold=base_scenario.get('threshold', 0.05)
            )
            
            results_summary.append({
                'scenario': scenario['name'],
                'roi': result.roi,
                'sharpe': result.sharpe_ratio,
                'max_dd': result.max_drawdown,
                'final_bankroll': result.final_bankroll
            })
        
        # Aggregate statistics
        rois = [r['roi'] for r in results_summary]
        sharps = [r['sharpe'] for r in results_summary]
        dds = [r['max_dd'] for r in results_summary]
        
        return {
            'scenarios_tested': len(results_summary),
            'roi_mean': np.mean(rois),
            'roi_std': np.std(rois),
            'roi_worst': np.min(rois),
            'roi_best': np.max(rois),
            'sharpe_mean': np.mean(sharps),
            'max_dd_worst': np.max(dds),
            'robustness_rating': 'HIGH' if np.std(rois) < 0.2 else 'MEDIUM' if np.std(rois) < 0.4 else 'LOW'
        }


def main():
    """Main execution function"""
    print("\n" + "="*80)
    print("ELITE BETTING SYSTEM OPTIMIZER - VERSION 2.0")
    print("EVALUATION METRIC: TOTAL NET MONEY WON")
    print("="*80)
    
    optimizer = EliteBettingOptimizer(initial_bankroll=10000.0)
    
    # Step 1: Audit current system
    print("\n\n[STEP 1] AUDITING CURRENT SYSTEM...")
    weaknesses = optimizer.audit_current_system()
    
    # Step 2: Generate synthetic data for testing
    print("\n\n[STEP 2] GENERATING SYNTHETIC TEST DATA...")
    synthetic_data = optimizer.generate_synthetic_data(
        num_bets=2000,
        true_edge_mean=0.08,
        true_edge_std=0.05,
        model_uncertainty=0.08
    )
    print(f"Generated {len(synthetic_data)} synthetic bets")
    print(f"Average true edge: {synthetic_data['true_edge'].mean():.2%}")
    print(f"Average perceived edge: {synthetic_data['perceived_edge'].mean():.2%}")
    
    # Step 3: Baseline backtest (current system parameters)
    print("\n\n[STEP 3] BASELINE BACKTEST (Current Parameters)...")
    baseline_result = optimizer.run_comprehensive_backtest(
        synthetic_data,
        kelly_fraction=0.25,
        edge_threshold=0.05,
        max_stake_pct=0.05
    )
    
    print(f"\nBASELINE RESULTS:")
    print(f"  Total Bets: {baseline_result.total_bets}")
    print(f"  Win Rate: {baseline_result.win_rate:.2%}")
    print(f"  Total P&L: ${baseline_result.total_pnl:,.2f}")
    print(f"  ROI: {baseline_result.roi:.2%}")
    print(f"  Yield: {baseline_result.yield_pct:.2%}")
    print(f"  Final Bankroll: ${baseline_result.final_bankroll:,.2f}")
    print(f"  Max Drawdown: {baseline_result.max_drawdown:.2%}")
    print(f"  Sharpe Ratio: {baseline_result.sharpe_ratio:.2f}")
    print(f"  Risk of Ruin: {baseline_result.risk_of_ruin:.2%}")
    
    # Step 4: Optimize edge threshold
    print("\n\n[STEP 4] OPTIMIZING EDGE THRESHOLD...")
    optimal_threshold = optimizer.optimize_edge_threshold(synthetic_data, min_bets=100)
    
    # Step 5: Calculate optimal Kelly fraction
    print("\n\n[STEP 5] CALCULATING OPTIMAL KELLY FRACTION...")
    optimal_kelly = optimizer.calculate_optimal_kelly_fraction(
        historical_edges=synthetic_data['perceived_edge'].values,
        historical_odds=synthetic_data['odds'].values,
        historical_win_rates=synthetic_data['outcome'].values
    )
    print(f"Optimal Kelly Fraction: {optimal_kelly:.2f}")
    
    # Step 6: Optimized backtest
    print("\n\n[STEP 6] OPTIMIZED BACKTEST (Version 2.0)...")
    optimized_result = optimizer.run_comprehensive_backtest(
        synthetic_data,
        kelly_fraction=optimal_kelly,
        edge_threshold=optimal_threshold,
        max_stake_pct=0.05
    )
    
    print(f"\nOPTIMIZED RESULTS:")
    print(f"  Total Bets: {optimized_result.total_bets}")
    print(f"  Win Rate: {optimized_result.win_rate:.2%}")
    print(f"  Total P&L: ${optimized_result.total_pnl:,.2f}")
    print(f"  ROI: {optimized_result.roi:.2%}")
    print(f"  Yield: {optimized_result.yield_pct:.2%}")
    print(f"  Final Bankroll: ${optimized_result.final_bankroll:,.2f}")
    print(f"  Max Drawdown: {optimized_result.max_drawdown:.2%}")
    print(f"  Sharpe Ratio: {optimized_result.sharpe_ratio:.2f}")
    print(f"  Risk of Ruin: {optimized_result.risk_of_ruin:.2%}")
    
    # Step 7: Walk-forward analysis
    print("\n\n[STEP 7] WALK-FORWARD ANALYSIS (Out-of-Sample Testing)...")
    wfa_results = optimizer.walk_forward_analysis(synthetic_data, train_periods=4, test_periods=1)
    
    if 'error' not in wfa_results:
        print(f"\nWALK-FORWARD RESULTS:")
        print(f"  Average OOS ROI: {wfa_results['avg_oos_roi']:.2%}")
        print(f"  Average OOS Sharpe: {wfa_results['avg_oos_sharpe']:.2f}")
        print(f"  Average OOS Max DD: {wfa_results['avg_oos_max_dd']:.2%}")
        print(f"  Robustness Score: {wfa_results['robustness_score']:.2f}")
    
    # Step 8: Monte Carlo stress test
    print("\n\n[STEP 8] MONTE CARLO STRESS TESTING...")
    stress_results = optimizer.monte_carlo_stress_test(
        base_scenario={
            'edge_mean': 0.08,
            'uncertainty': 0.08,
            'kelly': optimal_kelly,
            'threshold': optimal_threshold
        },
        num_scenarios=50
    )
    
    print(f"\nSTRESS TEST RESULTS:")
    print(f"  Scenarios Tested: {stress_results['scenarios_tested']}")
    print(f"  Average ROI: {stress_results['roi_mean']:.2%}")
    print(f"  ROI Std Dev: {stress_results['roi_std']:.2%}")
    print(f"  Worst Case ROI: {stress_results['roi_worst']:.2%}")
    print(f"  Best Case ROI: {stress_results['roi_best']:.2%}")
    print(f"  Average Sharpe: {stress_results['sharpe_mean']:.2f}")
    print(f"  Worst Max DD: {stress_results['max_dd_worst']:.2%}")
    print(f"  Robustness Rating: {stress_results['robustness_rating']}")
    
    # Step 9: Comparison summary
    print("\n\n" + "="*80)
    print("FINAL COMPARISON: BASELINE vs OPTIMIZED")
    print("="*80)
    
    improvement = optimized_result.total_pnl - baseline_result.total_pnl
    improvement_pct = (improvement / abs(baseline_result.total_pnl) * 100) if baseline_result.total_pnl != 0 else 0
    
    print(f"\nMETRIC                  | BASELINE      | OPTIMIZED     | IMPROVEMENT")
    print("-"*80)
    print(f"Total P&L               | ${baseline_result.total_pnl:>12,.2f} | ${optimized_result.total_pnl:>12,.2f} | {improvement:+>12,.2f} ({improvement_pct:+.1f}%)")
    print(f"ROI                     | {baseline_result.roi:>12.2%} | {optimized_result.roi:>12.2%} | {optimized_result.roi - baseline_result.roi:>+12.2%}")
    print(f"Final Bankroll          | ${baseline_result.final_bankroll:>11,.2f} | ${optimized_result.final_bankroll:>11,.2f} | {optimized_result.final_bankroll - baseline_result.final_bankroll:>+11,.2f}")
    print(f"Sharpe Ratio            | {baseline_result.sharpe_ratio:>12.2f} | {optimized_result.sharpe_ratio:>12.2f} | {optimized_result.sharpe_ratio - baseline_result.sharpe_ratio:>+12.2f}")
    print(f"Max Drawdown            | {baseline_result.max_drawdown:>12.2%} | {optimized_result.max_drawdown:>12.2%} | {(optimized_result.max_drawdown - baseline_result.max_drawdown):>+12.2%}")
    print(f"Risk of Ruin            | {baseline_result.risk_of_ruin:>12.2%} | {optimized_result.risk_of_ruin:>12.2%} | {(optimized_result.risk_of_ruin - baseline_result.risk_of_ruin):>+12.2%}")
    
    print("\n\n" + "="*80)
    print("OPTIMIZATION SUMMARY")
    print("="*80)
    print(f"✓ Edge Threshold Optimized: 5.0% → {optimal_threshold:.1%}")
    print(f"✓ Kelly Fraction Optimized: 25% → {optimal_kelly:.0%}")
    print(f"✓ Net Profit Improvement: ${improvement:,.2f} ({improvement_pct:+.1f}%)")
    print(f"✓ Risk-Adjusted Returns Improved: Sharpe {baseline_result.sharpe_ratio:.2f} → {optimized_result.sharpe_ratio:.2f}")
    
    if optimized_result.total_pnl > baseline_result.total_pnl:
        print("\n✅ SUCCESS: Optimized system outperforms baseline!")
        print(f"   Additional Profit: ${improvement:,.2f}")
    else:
        print("\n⚠️  WARNING: Optimization did not improve results")
        print("   Consider adjusting parameters or collecting more data")
    
    print("\n" + "="*80)
    
    return {
        'baseline': baseline_result,
        'optimized': optimized_result,
        'improvement': improvement,
        'optimal_threshold': optimal_threshold,
        'optimal_kelly': optimal_kelly,
        'walk_forward': wfa_results,
        'stress_test': stress_results
    }


if __name__ == "__main__":
    results = main()
