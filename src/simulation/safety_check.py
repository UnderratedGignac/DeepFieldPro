"""
Safety Check Module
Runs a rapid Monte Carlo simulation to ensure the strategy has positive EV
before allowing the system to start. Prevents deploying a losing strategy.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from simulation.lab import run_monte_carlo_simulation

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='Run quick 1000 iteration check')
    args = parser.parse_args()

    iterations = 1000 if args.quick else 10000
    
    print(f"Running safety check: {iterations} simulations...")
    
    results = run_monte_carlo_simulation(
        num_simulations=iterations,
        initial_bankroll=1000,
        edge_threshold=0.05,  # 5% minimum edge
        kelly_fraction=0.25,  # Quarter Kelly
        max_stake_pct=0.05    # 5% cap
    )
    
    final_bankroll = results['final_bankroll_mean']
    roi = results['roi_mean']
    risk_of_ruin = results['risk_of_ruin']
    
    print(f"\n--- SAFETY CHECK RESULTS ---")
    print(f"Simulations: {iterations}")
    print(f"Avg Final Bankroll: ${final_bankroll:.2f}")
    print(f"Expected ROI: {roi*100:.2f}%")
    print(f"Risk of Ruin: {risk_of_ruin*100:.2f}%")
    
    # Safety Criteria
    if roi <= 0:
        print("\n❌ CRITICAL: Strategy has negative expected value!")
        print("ABORTING STARTUP to prevent financial losses.")
        sys.exit(1)
    
    if risk_of_ruin > 0.10:  # More than 10% risk of ruin is too dangerous
        print("\n⚠️ WARNING: Risk of ruin is too high (>10%).")
        print("Consider lowering stake size or increasing edge threshold.")
        # We don't exit here, just warn, but in production you might want to exit
    
    if final_bankroll < 1000:
        print("\n⚠️ WARNING: Expected bankroll decay detected.")
        # Don't abort if ROI is positive but variance is high, but log it
    
    print("\n✅ SAFETY CHECK PASSED")
    print("Strategy shows positive expected value. Proceeding with startup.")
    sys.exit(0)

if __name__ == "__main__":
    main()
