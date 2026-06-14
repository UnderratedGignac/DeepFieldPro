from dataclasses import dataclass


@dataclass
class MarketVelocityChangedEvent:
    fixture_id: str
    market_type: str
    velocity_score: float
    acceleration: float
    timestamp: str


@dataclass
class MarketRegimeChangedEvent:
    fixture_id: str
    market_type: str
    old_regime: str
    new_regime: str
    timestamp: str


@dataclass
class EdgeDecayUpdatedEvent:
    fixture_id: str
    market_type: str
    half_life_ms: float
    timestamp: str


@dataclass
class ExecutionFailureEvent:
    exec_id: str
    failure_classification: str
    latency_ms: float
    market_regime: str
    timestamp: str


@dataclass
class ExecutionSurvivabilityUpdatedEvent:
    market_type: str
    new_fill_probability: float
    volatility_bucket: float
    timestamp: str
