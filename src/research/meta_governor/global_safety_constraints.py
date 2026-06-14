# mypy: ignore-errors
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class GlobalSafetyConstraints:
    """
    MGL Hard Constraints.
    Enforces maximum parameter updates, sudden regime dominance, and rapid threshold oscillations.
    """

    def __init__(self):
        self.MAX_THRESHOLD_DRIFT_PER_DAY = 0.05
        self.daily_drift_tracker = {"min_ev": 0.0, "p_fill": 0.0}
        # BUG FIX: Track which calendar date the drift budget is valid for.
        # Without this, the drift budget NEVER resets and blocks ALL updates after day 1.
        self._drift_date: str = datetime.timezone.utcnow().strftime("%Y-%m-%d")

    def _maybe_reset_daily_budget(self):
        today = datetime.timezone.utcnow().strftime("%Y-%m-%d")
        if today != self._drift_date:
            self.daily_drift_tracker = {"min_ev": 0.0, "p_fill": 0.0}
            self._drift_date = today

    def validate_apo_update(self, proposed_ev: float, current_ev: float) -> bool:
        """
        Prevents APO from making massive, destabilizing jumps in execution thresholds.
        """
        self._maybe_reset_daily_budget()
        drift = abs(proposed_ev - current_ev)

        if drift > 0.02:  # Hard constraint per update
            logger.warning(
                f"[SAFETY] Blocked APO Update! Proposed jump ({drift}) exceeds single-update cap."
            )
            return False

        if (
            self.daily_drift_tracker["min_ev"] + drift
            > self.MAX_THRESHOLD_DRIFT_PER_DAY
        ):
            logger.warning(
                "[SAFETY] Blocked APO Update! Exceeds max daily drift allowance."
            )
            return False

        # Accept update and track
        self.daily_drift_tracker["min_ev"] += drift
        return True


safety_constraints = GlobalSafetyConstraints()
