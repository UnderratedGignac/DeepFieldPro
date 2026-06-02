import asyncio
import logging
from src.autonomous_portfolio_evolution.apel_engine import apel_engine

logging.basicConfig(level=logging.INFO, format='%(message)s')

class APELSimulationLab:
    async def run_apel_cycle(self):
        print("\n--- SCENARIO 1: Stable Portfolio ---")
        # Simulate a good day for the core strategy
        telemetry_day1 = {
            "core_nba_props_v1": {
                "realized_ev": 150.0,
                "current_drawdown": 0.02,
                "decay_probability": 0.15
            }
        }
        apel_engine.evaluate_portfolio_lifecycle(telemetry_day1)
        
        print("\n--- SCENARIO 2: Structural Decay (Probation) ---")
        # Simulate edge decay starting
        telemetry_day2 = {
            "core_nba_props_v1": {
                "realized_ev": -50.0,
                "current_drawdown": 0.12,
                "decay_probability": 0.65
            }
        }
        apel_engine.evaluate_portfolio_lifecycle(telemetry_day2)
        
        print("\n--- SCENARIO 3: Strategy Failure & Evolution ---")
        # Simulate full structural failure
        telemetry_day3 = {
            "core_nba_props_v1": {
                "realized_ev": -300.0,
                "current_drawdown": 0.26, # Breached MAX_DRAWDOWN (0.25)
                "decay_probability": 0.88 # Breached DECAY_PROB (0.85)
            }
        }
        apel_engine.evaluate_portfolio_lifecycle(telemetry_day3)
        
        print(f"\nActive Strategies Post-Evolution: {apel_engine.get_active_strategies()}")

if __name__ == "__main__":
    asyncio.run(APELSimulationLab().run_apel_cycle())
