import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import asyncio
import logging
import random
# Add src root to pythonpath
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
from src.data_acquisition.execution_simulator import execution_sim  # noqa: E402
from src.data_acquisition.replay_analytics import ReplayAnalyticsDashboard  # noqa: E402
MARKETS = [
    "player_goal_anytime",
    "player_first_goalscorer",
    "player_shots_ou",
    "player_sot_ou",
    "player_card_yellow",
]
SCENARIOS = {
    "Baseline": (250, 750),
    "Mild": (750, 1500),
    "Moderate": (1500, 3000),
    "Severe": (3000, 6000),
    "Extreme": (6000, 12000),
}
def generate_stress_test_edges(num_edges=500):
    """
    Generates a large queue of simultaneous and sequential edges to stress test
    queue saturation and latency decay.
    """
    edges = []
    for i in range(num_edges):
        market = random.choice(MARKETS)
        # In a goalscorer market, edge is highly sensitive and volatility is high
        if "goal" in market:
            volatility = random.uniform(0.6, 1.0)
            theor_ev = random.uniform(1.0, 5.0)  # High theoretical EV on fresh lineups
        else:
            volatility = random.uniform(0.2, 0.6)
            theor_ev = random.uniform(0.5, 3.0)
        requested_odds = random.uniform(2.0, 5.0)
        bet = {
            "player": f"Player_{i}",
            "market": market,
            "odds": requested_odds,
            "priority_score": theor_ev,
            "confidence": 1.0,
            "time_since_lineup": random.randint(
                0, 10
            ),  # 0 to 10 seconds since lineup dropped
        }
        edges.append((bet, volatility))
    return edges
async def run_latency_stress_test():
    print("\n=== PHASE 5: LATENCY STRESS TESTING ===")
    edges_to_simulate = generate_stress_test_edges(1000)
    # We will track metrics per scenario
    scenario_reports = {}
    for scenario_name, delay_range in SCENARIOS.items():
        print(f"\n--- Running Scenario: {scenario_name} {delay_range}ms ---")
        # Create an isolated dashboard for this scenario
        dashboard = ReplayAnalyticsDashboard()
        for bet, volatility in edges_to_simulate:
            # Re-inject the original requested odds and priority score (to reset from previous loop)
            bet_copy = dict(bet)
            result = execution_sim.attempt_execution(
                bet_copy, market_volatility=volatility, delay_range=delay_range
            )
            # Enrich
            result["market"] = bet_copy["market"]
            result["confidence"] = bet_copy["confidence"]
            result["time_since_lineup"] = bet_copy["time_since_lineup"]
            dashboard.record_attempt(result)
        scenario_reports[scenario_name] = dashboard
    print("\n=======================================================")
    print("=== LATENCY COLLAPSE & EDGE SURVIVABILITY REPORT  ===")
    print("=======================================================")
    print(
        f"{'Scenario':<12} | {'Fill Rate':<10} | {'Theor EV':<10} | {'Realized EV':<12} | {'Realization %'}"
    )
    print("-" * 65)
    for name, dashboard in scenario_reports.items():
        stats = dashboard.metrics
        fill_rate = (stats["total_fills"] / stats["total_attempts"]) * 100
        theor = stats["theoretical_ev_sum"]
        realized = stats["realized_ev_sum"]
        rate = (realized / theor) * 100 if theor > 0 else 0
        print(
            f"{name:<12} | {fill_rate:>8.1f}% | {theor:>10.1f} | {realized:>12.1f} | {rate:>12.1f}%"
        )
    print("\n--- Market Stratification (Survivability) ---")
    print("Fill Rate by Market across Latency Profiles:")
    print(f"{'Market':<25} | {'Baseline':<8} | {'Moderate':<8} | {'Extreme':<8}")
    print("-" * 65)
    baseline_fills = scenario_reports["Baseline"].fills_by_market
    moderate_fills = scenario_reports["Moderate"].fills_by_market
    extreme_fills = scenario_reports["Extreme"].fills_by_market
    for market in MARKETS:
        def get_rate(f_dict):
            if market not in f_dict or f_dict[market]["attempts"] == 0:
                return 0.0
            return (f_dict[market]["fills"] / f_dict[market]["attempts"]) * 100
        b_rate = get_rate(baseline_fills)
        m_rate = get_rate(moderate_fills)
        e_rate = get_rate(extreme_fills)
        print(f"{market:<25} | {b_rate:>7.1f}% | {m_rate:>7.1f}% | {e_rate:>7.1f}%")
if __name__ == "__main__":
    asyncio.run(run_latency_stress_test())