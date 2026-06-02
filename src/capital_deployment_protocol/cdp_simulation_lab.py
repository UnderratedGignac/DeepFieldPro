import asyncio
import logging
import sys

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

from src.capital_deployment_protocol.deployment_orchestrator import cdp_orchestrator
from src.capital_deployment_protocol.schemas import CapitalAllocationRequest

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

class CDPSimulationLab:
    """
    Simulates the system transitioning safely from SHADOW to MICRO scaling,
    evaluating position sizing under different regimes.
    """
    async def run_cdp_flow(self):
        # 1. Day 15: System has been in SHADOW mode for 14 days with 0 drawdown.
        # RVL gives passing signal.
        cdp_orchestrator.state = cdp_orchestrator.state.model_copy(update={"days_in_phase": 14})
        
        # Trigger daily lifecycle
        cdp_orchestrator.process_daily_lifecycle(is_rvl_passing=True, current_drawdown=0.0)
        
        # 2. Execution Engine requests capital for a high EV bet in a stable regime
        req1 = CapitalAllocationRequest(
            trace_id="bet-123",
            predicted_ev=0.15,
            regime="stable",
            base_stake=500.0, # Strategy wants to bet $500
            correlation_risk_score=0.1,
            p_fill=0.9
        )
        
        allowed_stake = cdp_orchestrator.request_capital_execution(req1, rvl_signal="READY_FOR_CAPITAL")
        logger.info(f"\n[EXECUTION ENGINE] Strategy requested $500. CDP Authorized: ${allowed_stake:.2f}")
        
        # 3. Execution Engine requests capital for a highly fragile panic regime bet
        req2 = CapitalAllocationRequest(
            trace_id="bet-124",
            predicted_ev=0.40,
            regime="panic",
            base_stake=500.0, # Strategy wants to bet $500
            correlation_risk_score=0.5,
            p_fill=0.2
        )
        
        allowed_stake_2 = cdp_orchestrator.request_capital_execution(req2, rvl_signal="READY_FOR_CAPITAL")
        logger.info(f"[EXECUTION ENGINE] Strategy requested $500 (Panic Regime). CDP Authorized: ${allowed_stake_2:.2f}")
        
        # 4. Crisis Simulator: System hits a 12% drawdown in MICRO Phase (Limit was 5%)
        logger.info("\n--- SIMULATING SUDDEN SYSTEM DRAWDOWN VIOLATION ---")
        cdp_orchestrator.process_daily_lifecycle(is_rvl_passing=True, current_drawdown=0.12)
        
        # Try to bet again
        allowed_stake_3 = cdp_orchestrator.request_capital_execution(req1, rvl_signal="READY_FOR_CAPITAL")
        logger.info(f"[EXECUTION ENGINE] Attempted to bet post-crisis. CDP Authorized: ${allowed_stake_3:.2f}")

if __name__ == "__main__":
    lab = CDPSimulationLab()
    asyncio.run(lab.run_cdp_flow())
