from enum import Enum
from pydantic import BaseModel
from typing import Dict, Any


class StrategyStatus(Enum):
    ACTIVE = "ACTIVE"
    PROBATION = "PROBATION"
    RETIRED = "RETIRED"


class StrategyGenome(BaseModel):
    strategy_id: str
    sport: str
    market_type: str
    base_model_version: str
    hyperparameters: Dict[str, Any]


class StrategyState(BaseModel):
    genome: StrategyGenome
    status: StrategyStatus
    live_days: int
    total_realized_ev: float
    current_drawdown: float
    decay_probability: float
