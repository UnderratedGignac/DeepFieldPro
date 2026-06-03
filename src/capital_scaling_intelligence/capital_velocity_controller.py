import logging

logger = logging.getLogger(__name__)

class CapitalVelocityController:
    """
    Controls HOW FAST capital is increased or decreased over time.
    Prevents exponential runaway scaling and sudden capital doubling events.
    """
    def __init__(self):
        self.MAX_DAILY_ACCELERATION = 0.02 # Max 2% increase in capital scaling velocity per day
        self.MAX_VELOCITY = 0.10 # Hard cap: Never scale exposure faster than 10% per cycle

    def compute_safe_velocity(self, current_velocity: float, target_velocity: float) -> float:
        """
        Damps acceleration to prevent scaling shocks.
        """
        delta = target_velocity - current_velocity
        
        # If we need to scale down, we allow faster deceleration (safety)
        if delta < 0:
            allowed_delta = max(delta, -0.05) # Max 5% drop in velocity per cycle
        else:
            # If scaling up, strictly bound acceleration
            allowed_delta = min(delta, self.MAX_DAILY_ACCELERATION)
            
        new_velocity = current_velocity + allowed_delta
        
        # Enforce absolute ceiling
        final_velocity = min(max(new_velocity, -self.MAX_VELOCITY), self.MAX_VELOCITY)
        
        logger.debug(f"[VELOCITY CONTROLLER] Current: {current_velocity:.3f} | Target: {target_velocity:.3f} | Approved: {final_velocity:.3f}")
        return final_velocity

velocity_controller = CapitalVelocityController()
