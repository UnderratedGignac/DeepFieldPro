import asyncio
import logging
import sys
import random

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

from src.portfolio_optimization.capital_allocation_engine import capital_engine
from src.data_acquisition.live_execution.predictive_layer.execution_policy_agent import policy_agent

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

class TodaysGamesSimulation:
    """
    Feeds today's live odds through the DeepFieldPro Quantitative Pipeline.
    Evaluates edges, regimes, and capital allocation to determine the final bets.
    """
    async def run_live_feed(self):
        logger.info("==========================================================")
        logger.info("=== DEEPFIELDPRO: LIVE GAME ANALYSIS (TODAY'S FIXTURES) ===")
        logger.info("==========================================================")
        
        # Mocking live data for today's fixtures
        # E.g., Real Madrid vs Borussia Dortmund (UCL)
        live_opportunities = [
            {
                "fixture_id": "UCL_FINAL_2024",
                "market": "player_goal_anytime",
                "player": "Vinicius Junior",
                "odds": 2.80,
                "expected_ev": 0.18,
                "p_fill": 0.45,  # High risk of suspension
                "regime": "panic", # Lineups just dropped
                "velocity": 0.95
            },
            {
                "fixture_id": "UCL_FINAL_2024",
                "market": "player_shots_ou",
                "player": "Toni Kroos",
                "odds": 1.95,
                "expected_ev": 0.12,
                "p_fill": 0.85,  # Stable market
                "regime": "stable",
                "velocity": 0.20
            },
            {
                "fixture_id": "UCL_FINAL_2024",
                "market": "player_card_yellow",
                "player": "Dani Carvajal",
                "odds": 3.50,
                "expected_ev": 0.25,
                "p_fill": 0.70,
                "regime": "reactive",
                "velocity": 0.50
            },
            {
                "fixture_id": "UCL_FINAL_2024",
                "market": "player_first_goalscorer",
                "player": "Niclas Fullkrug",
                "odds": 7.50,
                "expected_ev": 0.35,
                "p_fill": 0.15, # Extremely fragile
                "regime": "panic",
                "velocity": 0.90
            }
        ]
        
        logger.info("\n[SCANNING LIVE OPPORTUNITIES]")
        for opp in live_opportunities:
            logger.info(f"\nEvaluating: {opp['player']} - {opp['market']} @ {opp['odds']}")
            
            # 1. RL Policy Agent Routing
            action = policy_agent.decide_policy(
                market_type=opp['market'], 
                regime=opp['regime'], 
                p_fill=opp['p_fill'], 
                velocity=opp['velocity'], 
                ev=opp['expected_ev']
            )
            
            # 2. Capital Allocation Engine
            stake = capital_engine.allocate_capital(
                bet_metadata=opp, 
                expected_ev=opp['expected_ev'], 
                p_fill=opp['p_fill'], 
                odds=opp['odds'], 
                regime=opp['regime']
            )
            
            # 3. Final Decision
            if action == "SKIP" or stake <= 5.0:
                logger.info(f"-> VERDICT: REJECTED (Action: {action}, Allocated: ${stake})")
            else:
                logger.info(f"-> VERDICT: APPROVED (Action: {action}, Allocated: ${stake})")

if __name__ == "__main__":
    app = TodaysGamesSimulation()
    asyncio.run(app.run_live_feed())
