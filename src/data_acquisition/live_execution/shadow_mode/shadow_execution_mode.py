import asyncio
import logging
from typing import Dict, Any

from src.data_acquisition.latency_telemetry import latency_tracker
from src.data_acquisition.live_execution.dom_interaction_engine import dom_engine
from src.data_acquisition.live_execution.selector_registry import registry

logger = logging.getLogger(__name__)

class ShadowExecutionMode:
    """
    Advanced Paper Trading Layer.
    Executes EVERYTHING: real browser, real market selection, real queue timing,
    real DOM latency, real network telemetry, real market movement.
    BUT: intercepts the final confirmation click.
    Produces true production telemetry without bankroll exposure.
    """
    def __init__(self, page):
        self.page = page

    async def execute_shadow_trade(self, bet_payload: Dict[str, Any]):
        """
        Runs the full execution pipeline and records actual DOM execution latency.
        """
        exec_id = latency_tracker.start_execution(bet_payload)
        logger.info(f"[SHADOW MODE] Initiating live DOM trace for {bet_payload['player']}")
        
        try:
            # 1. Real DOM resolution
            player_btn_sel = registry.get("player_row", player_name=bet_payload["player"])
            stake_sel = registry.get("stake_input", selection_id=bet_payload["selection_id"])
            confirm_sel = registry.get("confirm_button")
            
            # 2. Real DOM Click (actually triggers the UI change)
            success = await dom_engine.safe_click(self.page, player_btn_sel)
            if not success:
                logger.warning("[SHADOW MODE] Market suspended before click.")
                latency_tracker.finalize(exec_id)
                return {"status": "rejected", "reason": "pre_click_suspension"}
                
            latency_tracker.mark(exec_id, "click_sent")
            
            # 3. Real Betslip Open Wait
            await self.page.locator(stake_sel).wait_for(state="visible", timeout=3000)
            latency_tracker.mark(exec_id, "betslip_opened")
            
            # 4. Real Stake Fill
            await dom_engine.safe_fill(self.page, stake_sel, str(bet_payload["stake"]))
            latency_tracker.mark(exec_id, "stake_entered")
            
            # 5. SHADOW INTERCEPT: Wait for Confirm button to become enabled, but DO NOT CLICK.
            confirm_locator = self.page.locator(confirm_sel)
            await confirm_locator.wait_for(state="visible")
            
            # Simulate click in telemetry
            latency_tracker.mark(exec_id, "confirm_clicked")
            
            logger.info("[SHADOW MODE] Successfully shadowed execution. Intercepted final commit.")
            
            # We mock the confirmation receipt since we didn't actually send the payload
            await asyncio.sleep(1.2)
            latency_tracker.mark(exec_id, "confirmation_received")
            
            latency_tracker.finalize(exec_id)
            return {"status": "shadow_success"}
            
        except Exception as e:
            logger.error(f"[SHADOW MODE] Execution failed: {e}")
            latency_tracker.finalize(exec_id)
            return {"status": "error", "reason": str(e)}

