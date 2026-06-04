from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum


class RolloutPhase(str, Enum):
    PHASE_0_SHADOW = "SHADOW"
    PHASE_1_MICRO = "MICRO"
    PHASE_2_LIMITED = "LIMITED"
    PHASE_3_PRODUCTION = "PRODUCTION"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    SHUTDOWN_REQUIRED = "SHUTDOWN_REQUIRED"


class DeploymentState(BaseModel):
    """
    Tracks the current state of the Capital Deployment Protocol.
    """

    model_config = ConfigDict(frozen=True)

    current_phase: RolloutPhase = RolloutPhase.PHASE_0_SHADOW
    max_capital_allocation: float = 0.0
    current_health: HealthStatus = HealthStatus.HEALTHY
    days_in_phase: int = 0
    phase_drawdown_pct: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.timezone.utcnow)


class CapitalAllocationRequest(BaseModel):
    """
    Request from the execution engine to allocate capital for a specific bet.
    """

    trace_id: str
    predicted_ev: float
    regime: str
    base_stake: float
    correlation_risk_score: float
    p_fill: float
