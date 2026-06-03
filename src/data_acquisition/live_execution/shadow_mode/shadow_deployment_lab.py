import asyncio
import logging
import random
import sys

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

from src.data_acquisition.live_execution.shadow_mode.execution_drift_monitor import (
    drift_monitor,
)
from src.data_acquisition.live_execution.shadow_mode.sportsbook_adversarial_model import (
    adversarial_model,
)
from src.data_acquisition.live_execution.shadow_mode.account_behavior_profile import (
    account_profile,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class ShadowDeploymentLab:
    """
    Simulates a longitudinal run of the system executing in shadow mode over several hours.
    Injects progressive latency degradation and selective suspensions to trigger the adversarial models.
    """

    async def run_longitudinal_test(self):
        logger.info("==========================================================")
        logger.info("=== SHADOW DEPLOYMENT & ADVERSARIAL TELEMETRY LAB ======")
        logger.info("==========================================================")

        logger.info("\n--- Phase 1: Normal Operation (Hour 1) ---")
        for i in range(25):
            latency = random.uniform(1200, 1600)
            drift_monitor.log_execution_latency(latency)

        risk = adversarial_model.evaluate_adversarial_risk(
            recent_rejections=1, avg_confirmation_delay=1400.0
        )
        account_profile.log_session_telemetry(1400.0, 0.04, 0.1, 1.0)
        logger.info(f"Adversarial Risk Level: {risk}")

        logger.info("\n--- Phase 2: Sportsbook Adaptation (Hour 3) ---")
        logger.info(
            "Injecting progressive confirmation delays (Throttling Signature)..."
        )
        # Simulate bookmaker slowing down our specific account
        for i in range(25):
            latency = random.uniform(1800, 2600)
            drift_monitor.log_execution_latency(latency)

        risk = adversarial_model.evaluate_adversarial_risk(
            recent_rejections=6, avg_confirmation_delay=2200.0
        )
        account_profile.log_session_telemetry(2200.0, 0.24, 0.6, 3.0)
        logger.info(f"Adversarial Risk Level: {risk}")


if __name__ == "__main__":
    lab = ShadowDeploymentLab()
    asyncio.run(lab.run_longitudinal_test())
