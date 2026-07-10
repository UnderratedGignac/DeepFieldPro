"""
Comprehensive Betting System Stress Test
Evaluates the entire system under extreme conditions to ensure profitability.
"""
import sys
import os

# Add both src and root workspace to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from simulation.lab import run_monte_carlo_simulation

def run_stress_tests():
    print("=" * 60)
    print("COMPREHENSIVE BETTING SYSTEM STRESS TEST")
    print("=" * 60)
    
    test_scenarios = [
        {
            "name": "Baseline (Quarter Kelly, 5% Edge)",
            "params": {"edge_threshold": 0.05, "kelly_fraction": 0.25, "max_stake_pct": 0.05},
            "iterations": 5000
        },
        {
            "name": "Conservative (Half Kelly, 8% Edge)",
            "params": {"edge_threshold": 0.08, "kelly_fraction": 0.50, "max_stake_pct": 0.03},
            "iterations": 5000
        },
        {
            "name": "Aggressive (Full Kelly, 5% Edge)",
            "params": {"edge_threshold": 0.05, "kelly_fraction": 1.0, "max_stake_pct": 0.10},
            "iterations": 5000
        },
        {
            "name": "High Confidence Only (10% Edge)",
            "params": {"edge_threshold": 0.10, "kelly_fraction": 0.25, "max_stake_pct": 0.05},
            "iterations": 5000
        },
        {
            "name": "Market Crash Simulation (Reduced Edge)",
            "params": {"edge_threshold": 0.03, "kelly_fraction": 0.25, "max_stake_pct": 0.05},
            "iterations": 5000,
            "edge_decay": 0.5  # Simulate model degradation
        }
    ]
    
    results_summary = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n[{i}/{len(test_scenarios)}] Testing: {scenario['name']}")
        print("-" * 40)
        
        edge_decay = scenario.get('edge_decay', 1.0)
        
        results = run_monte_carlo_simulation(
            num_simulations=scenario['iterations'],
            initial_bankroll=1000,
            edge_threshold=scenario['params']['edge_threshold'],
            kelly_fraction=scenario['params']['kelly_fraction'],
            max_stake_pct=scenario['params']['max_stake_pct'],
            edge_decay=edge_decay
        )
        
        roi = results['roi_mean'] * 100
        final_bankroll = results['final_bankroll_mean']
        risk_ruin = results['risk_of_ruin'] * 100
        sharpe = results.get('sharpe_ratio', 0)
        
        results_summary.append({
            "name": scenario['name'],
            "roi": roi,
            "bankroll": final_bankroll,
            "risk_ruin": risk_ruin,
            "sharpe": sharpe
        })
        
        status = "✅ PROFITABLE" if roi > 0 else "❌ LOSING"
        print(f"ROI: {roi:.2f}% {status}")
        print(f"Avg Final Bankroll: ${final_bankroll:.2f}")
        print(f"Risk of Ruin: {risk_ruin:.2f}%")
        print(f"Sharpe Ratio: {sharpe:.2f}")
    
    # Summary Table
    print("\n" + "=" * 60)
    print("SUMMARY TABLE (Sorted by ROI)")
    print("=" * 60)
    print(f"{'Strategy':<35} {'ROI %':>10} {'Bankroll':>12} {'Risk %':>10} {'Sharpe':>8}")
    print("-" * 60)
    
    sorted_results = sorted(results_summary, key=lambda x: x['roi'], reverse=True)
    
    for res in sorted_results:
        status_icon = "✅" if res['roi'] > 0 else "❌"
        print(f"{status_icon} {res['name']:<33} {res['roi']:>9.2f} ${res['bankroll']:>10.2f} {res['risk_ruin']:>9.2f} {res['sharpe']:>8.2f}")
    
    # Find best strategy
    best = sorted_results[0]
    print("\n" + "=" * 60)
    if best['roi'] > 10:
        print(f"🏆 RECOMMENDED STRATEGY: {best['name']}")
        print(f"   Expected ROI: {best['roi']:.2f}%")
        print(f"   Risk of Ruin: {best['risk_ruin']:.2f}%")
        print(f"   SYSTEM READY FOR DEPLOYMENT")
    elif best['roi'] > 0:
        print(f"⚠️ MARGINAL STRATEGY: {best['name']}")
        print(f"   Expected ROI: {best['roi']:.2f}% (Low but positive)")
        print(f"   Consider increasing edge threshold or improving model")
    else:
        print(f"❌ CRITICAL: No profitable strategy found!")
        print(f"   Best ROI: {best['roi']:.2f}%")
        print(f"   DO NOT DEPLOY - Model needs retraining")
        return False
    
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = run_stress_tests()
    sys.exit(0 if success else 1)
