from pydantic import BaseModel, ConfigDict
from enum import Enum


class CompoundingRegime(str, Enum):
    COMPOUNDING = "COMPOUNDING"
    NEUTRAL = "NEUTRAL"
    DECAY = "DECAY"


class ScalingDecision(str, Enum):
    SCALE_UP = "SCALE_UP"
    HOLD = "HOLD"
    SCALE_DOWN = "SCALE_DOWN"
    FREEZE_SCALING = "FREEZE_SCALING"


class ACSIScalingState(BaseModel):
    """
    Tracks the trajectory state of the capital optimization loop.
    """

    model_config = ConfigDict(frozen=True)

    current_compounding_regime: CompoundingRegime = CompoundingRegime.NEUTRAL
    long_horizon_ev_trend: float = 0.0
    scaling_velocity: float = 0.0  # Rate of capital expansion
    current_decision: ScalingDecision = ScalingDecision.HOLD
