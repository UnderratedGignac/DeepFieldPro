import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class PolicyDecisionEvent(BaseModel):
    """
    Phase 0: Standardize event logging.
    Every bet decision MUST carry a trace_id to link decision -> execution -> outcome.
    """
    model_config = ConfigDict(frozen=True)

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    fixture_id: str
    market_type: str
    player_name: str
    decision_action: str # "EXECUTE", "SKIP", "DELAY", "BATCH"
    odds_at_decision: float
    regime_state: str
    predicted_ev: float
    predicted_p_fill: float
    allocated_stake: float

class ExecutionOutcomeEvent(BaseModel):
    """
    Records the physical outcome of the decision.
    """
    model_config = ConfigDict(frozen=True)

    trace_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    fill_status: str # "FILLED", "REJECTED_LATENCY", "REJECTED_ODDS", "SKIPPED"
    actual_latency_ms: float
    actual_fill_odds: Optional[float] = None
    slippage_ticks: int = 0
    
class MarketSnapshotEvent(BaseModel):
    """
    Records the final truth of the market (Closing Line).
    Resolved T+24h or at kickoff.
    """
    model_config = ConfigDict(frozen=True)
    
    trace_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    closing_odds: float
    market_status: str # "SETTLED", "VOIDED"
