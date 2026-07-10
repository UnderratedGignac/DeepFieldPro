import logging

from src.capital_deployment_protocol.schemas import HealthStatus
from src.capital_deployment_protocol.cdp_config import cdp_config

logger = logging.getLogger(__name__)


class LiveCapitalSwitch:
    """
    A hard boundary safety system. Instantly disables execution if critical thresholds are breached.
    Overrides all ML, MGL, and APO systems.
    """

    def __init__(self):
        self.is_execution_enabled = False

    def evaluate_safety_lock(
        self, health_status: HealthStatus, rvl_signal: str
    ) -> bool:
        """
        Determines if the physical execution switch should remain ON.
        Uses configurable allowed RVL signals from cdp_config.
        """
        if health_status in [HealthStatus.CRITICAL, HealthStatus.SHUTDOWN_REQUIRED]:
            logger.critical(
                "[KILL SWITCH] ENGAGED! System health critical. Execution offline."
            )
            self.is_execution_enabled = False
            return False

        if rvl_signal not in cdp_config.ALLOWED_RVL_SIGNALS:
            logger.warning(
                f"[KILL SWITCH] RVL Signal is {rvl_signal}. Execution offline."
            )
            self.is_execution_enabled = False
            return False

        self.is_execution_enabled = True
        return True


kill_switch = LiveCapitalSwitch()
