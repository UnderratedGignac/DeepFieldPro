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
        # Belgium vs Croatia (International Fixture)
        live_opportunities = [
            {
                "fixture_id": "BEL_CRO_2026",
                "market": "player_goal_anytime",
                "player": "Romelu Lukaku",
                "odds": 2.20,
                "expected_ev": 0.15,
                "p_fill": 0.80,  # Stable market
                "regime": "stable",
                "velocity": 0.30
            },
            {
                "fixture_id": "BEL_CRO_2026",
                "market": "player_shots_ou",
                "player": "Kevin De Bruyne",
                "odds": 1.85,
                "expected_ev": 0.08,
                "p_fill": 0.90,  # Highly liquid
                "regime": "stable",
                "velocity": 0.10
            },
            {
                "fixture_id": "BEL_CRO_2026",
                "market": "player_card_yellow",
                "player": "Amadou Onana",
                "odds": 2.90,
                "expected_ev": 0.22,
                "p_fill": 0.30, # High risk of suspension
                "regime": "panic",
                "velocity": 0.85
            },
            {
                "fixture_id": "BEL_CRO_2026",
                "market": "player_passes_ou",
                "player": "Josko Gvardiol",
                "odds": 1.90,
                "expected_ev": 0.04, # Low EV
                "p_fill": 0.85, 
                "regime": "stable",
                "velocity": 0.15
            }
        ]
        
        logger.info("\n[SCANNING LIVE OPPORTUNITIES]")
        placed_bets = []
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
                logger.info(f"-> VERDICT: APPROVED (Action: {action}, Allocated: ${stake:.2f})")
                opp['stake'] = stake
                placed_bets.append(opp)
                
        logger.info("\n==========================================================")
        logger.info("=== FAST-FORWARD: MATCHES COMPLETED. SETTLING BETS... ===")
        logger.info("==========================================================")
        
        total_staked = 0.0
        total_pnl = 0.0
        
        for bet in placed_bets:
            # Simulate real-world outcome based on fair probability
            # The edge is expected_ev. True Prob = (1 + EV) / odds
            true_prob = (1.0 + bet['expected_ev']) / bet['odds']
            
            # Did the bet win?
            won = random.random() < true_prob
            
            stake = bet['stake']
            total_staked += stake
            
            if won:
                profit = stake * (bet['odds'] - 1.0)
                total_pnl += profit
                logger.info(f"✅ WON : {bet['player']} ({bet['market']}) @ {bet['odds']:.2f} -> +${profit:.2f}")
            else:
                total_pnl -= stake
                logger.info(f"❌ LOST: {bet['player']} ({bet['market']}) @ {bet['odds']:.2f} -> -${stake:.2f}")
                
        roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0.0
        
        logger.info("\n==========================================================")
        logger.info(f"=== END OF DAY SUMMARY ===")
        logger.info(f"Total Staked : ${total_staked:.2f}")
        logger.info(f"Total P&L    : ${total_pnl:+.2f}")
        logger.info(f"ROI          : {roi:+.2f}%")
        logger.info("==========================================================")

if __name__ == "__main__":
    app = TodaysGamesSimulation()
    asyncio.run(app.run_live_feed())
