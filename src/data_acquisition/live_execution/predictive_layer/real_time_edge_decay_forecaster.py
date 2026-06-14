import logging

from src.data_acquisition.live_execution.adaptive_layer.edge_decay_predictor import (
    decay_predictor,
)

logger = logging.getLogger(__name__)


class RealTimeEdgeDecayForecaster:
    """
    Makes edge decay predictive. Forecasts Edge(t + delta_t) before execution occurs.
    """

    def __init__(self):
        pass

    def forecast_edge_at_execution(
        self,
        market_type: str,
        current_ev: float,
        estimated_execution_latency_sec: float,
        regime: str,
    ) -> float:
        """
        Answers: 'Will this edge still exist by the time the click completes?'
        """
        # Call the foundational exponential decay model
        future_edge = decay_predictor.predict_remaining_edge(
            market_type=market_type,
            initial_ev=current_ev,
            time_elapsed_sec=estimated_execution_latency_sec,
            regime=regime,
        )

        logger.debug(
            f"[DECAY FORECAST] {market_type}: EV {current_ev:.3f} -> EV {future_edge:.3f} (after {estimated_execution_latency_sec}s delay)"
        )
        return future_edge


real_time_decay_forecaster = RealTimeEdgeDecayForecaster()
