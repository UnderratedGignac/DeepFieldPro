import asyncio
import logging
import sys
import numpy as np

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

from src.ml.online_learning.concept_drift_monitor import drift_monitor
from src.adversarial_detection.hidden_markov_throttle_detector import hmm_detector
from src.risk_engine.conditional_var_simulator import cvar_simulator
from src.execution_cluster.actor_orchestrator import orchestrator
from src.meta_research.meta_research_governor import meta_governor

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class InstitutionalDeploymentLab:
    """
    Simulates the interaction between all massive institutional ML and Risk systems.
    """

    async def run_institutional_ecosystem(self):
        logger.info("==========================================================")
        logger.info("=== INSTITUTIONAL QUANTITATIVE RESEARCH DEPLOYMENT LAB ===")
        logger.info("==========================================================")

        logger.info("\n--- Phase 1: Institutional Risk Engine (CVaR) ---")
        # Stress testing a correlated batch of bets across 10,000 Monte Carlo paths
        expected_win_rates = [0.45, 0.50, 0.35, 0.60, 0.40]
        expected_odds = [2.3, 2.1, 3.0, 1.75, 2.6]
        cvar_metrics = cvar_simulator.run_monte_carlo_stress_test(
            current_bankroll=10000.0,
            expected_win_rates=expected_win_rates,
            expected_odds=expected_odds,
        )
        logger.info(
            f"Calculated 95% Expected Tail Loss (CVaR): ${cvar_metrics['cvar_dollar']}"
        )

        logger.info("\n--- Phase 2: Online Learning (Concept Drift) ---")
        # Bookmaker introduces artificial lag, shifting latency from N(1300, 50) to N(2200, 100)
        baseline_latency = np.random.normal(1300, 50, 1000).tolist()
        recent_latency = np.random.normal(
            2200, 100, 100
        ).tolist()  # Sudden regime shift
        drift_status = drift_monitor.evaluate_drift(baseline_latency, recent_latency)

        logger.info("\n--- Phase 3: Meta-Research Governor ---")
        # Governor ingests the catastrophic drift and retires the strategy
        if drift_status["status"] == "DRIFT_DETECTED":
            meta_governor.evaluate_strategy_health(
                "goalscorer_momentum_v1",
                recent_drawdown=0.05,
                psi_drift=drift_status["psi"],
            )
        logger.info(
            f"Remaining Capital Weight for Strategy: {meta_governor.get_allocated_weight('goalscorer_momentum_v1')}"
        )

        logger.info("\n--- Phase 4: Adversarial HMM Detection ---")
        # Ingesting the latency and failure into the Hidden Markov Model
        hmm_detector.update_belief(execution_latency=2300, rejection_flag=True)
        hmm_detector.update_belief(execution_latency=2500, rejection_flag=True)
        p_restricted = hmm_detector.get_restriction_probability()
        logger.info(f"P(Account Restricted | Recent Behavior): {p_restricted*100:.1f}%")

        logger.info("\n--- Phase 5: Execution Cluster Circuit Breaker ---")

        # Simulating repeated worker failures to trigger the circuit breaker
        async def mock_fail(payload):
            return {"status": "error"}

        await orchestrator.execute_task("route_A", {}, mock_fail)
        await orchestrator.execute_task("route_A", {}, mock_fail)
        await orchestrator.execute_task("route_A", {}, mock_fail)

        # 4th attempt should be blocked instantly
        res = await orchestrator.execute_task("route_A", {}, mock_fail)
        logger.info(f"Route Execution Result: {res['status']}")


if __name__ == "__main__":
    lab = InstitutionalDeploymentLab()
    asyncio.run(lab.run_institutional_ecosystem())
