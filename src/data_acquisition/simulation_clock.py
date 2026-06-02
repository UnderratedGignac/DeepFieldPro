# simulation_clock.py
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SimulationClock:
    """
    Overrides system time during backtesting.
    Ensures absolute zero future information leakage by forcing 
    all subsystems to consume simulated time.
    """
    def __init__(self):
        self.is_simulation = False
        self._current_sim_time = None

    def enable_simulation_mode(self, start_time: datetime):
        self.is_simulation = True
        self._current_sim_time = start_time
        logger.info(f"[CLOCK] Simulation mode enabled. Clock set to: {start_time.isoformat()}")

    def disable_simulation_mode(self):
        self.is_simulation = False
        self._current_sim_time = None
        logger.info("[CLOCK] Simulation mode disabled. Returning to wall-clock time.")

    def advance_to(self, target_time: datetime):
        if not self.is_simulation:
            raise RuntimeError("Cannot advance clock when not in simulation mode.")
        if self._current_sim_time and target_time < self._current_sim_time:
            raise ValueError("Simulation clock cannot move backwards.")
            
        self._current_sim_time = target_time

    def now(self) -> datetime:
        """
        All systems should call this instead of datetime.now(timezone.utc)
        """
        if self.is_simulation and self._current_sim_time:
            return self._current_sim_time
        return datetime.now(timezone.utc)

sim_clock = SimulationClock()
