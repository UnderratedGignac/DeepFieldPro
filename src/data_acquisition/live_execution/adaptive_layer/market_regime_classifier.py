import logging
from typing import Dict

from .adaptive_events import MarketRegimeChangedEvent, MarketVelocityChangedEvent

logger = logging.getLogger(__name__)


class MarketRegimeClassifier:
    """
    Classifies markets into structural regimes: stable, reactive, panic, frozen, stale, high-frequency-volatility.
    """

    def __init__(self):
        # Dict[fixture_id -> Dict[market_type -> current_regime]]
        self.regimes: Dict[str, Dict[str, str]] = {}

    def classify(self, event: MarketVelocityChangedEvent, dispatcher) -> str:
        fixture_id = event.fixture_id
        market_type = event.market_type
        velocity = event.velocity_score

        if fixture_id not in self.regimes:
            self.regimes[fixture_id] = {}

        old_regime = self.regimes[fixture_id].get(market_type, "stable")

        # Classification thresholds
        if velocity > 20.0:
            new_regime = "panic"
        elif velocity > 10.0:
            new_regime = "high-frequency-volatility"
        elif velocity > 3.0:
            new_regime = "reactive"
        elif velocity < 0.1:
            new_regime = "stale"
        else:
            new_regime = "stable"

        if new_regime != old_regime:
            self.regimes[fixture_id][market_type] = new_regime
            logger.info(
                f"[REGIME] {fixture_id} | {market_type} shifted from {old_regime} -> {new_regime}"
            )

            regime_event = MarketRegimeChangedEvent(  # noqa: F841
                fixture_id=fixture_id,
                market_type=market_type,
                old_regime=old_regime,
                new_regime=new_regime,
                timestamp=event.timestamp,
            )
            # dispatcher.emit(regime_event)

        return new_regime


regime_classifier = MarketRegimeClassifier()
