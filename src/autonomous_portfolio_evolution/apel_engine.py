import logging
import uuid
from typing import Dict, List
from src.autonomous_portfolio_evolution.schemas import StrategyState, StrategyStatus, StrategyGenome

logger = logging.getLogger(__name__)

class AutonomousPortfolioEvolutionLayer:
    """
    W6 FIX: Autonomous Portfolio Evolution Layer (APEL).
    Responsible for dynamically managing the lifecycle of multiple strategies.
    Retires strategies that structurally decay and spawns new variants to replace them.
    """
    def __init__(self):
        self.active_strategies: Dict[str, StrategyState] = {}
        
        # Hard limits on portfolio size to bound compute/capital fragmentation
        self.MAX_ACTIVE_STRATEGIES = 5
        
        # Thresholds for pruning
        self.RETIRE_DECAY_PROB = 0.85     # Very high confidence of structural decay
        self.RETIRE_MAX_DRAWDOWN = 0.25   # Hard stop on strategy-level drawdown
        
        self._initialize_core_portfolio()

    def _initialize_core_portfolio(self):
        """Bootstraps the initial portfolio with the primary strategy."""
        core_genome = StrategyGenome(
            strategy_id="core_nba_props_v1",
            sport="NBA",
            market_type="PLAYER_PROPS",
            base_model_version="xgboost_v4.2",
            hyperparameters={"kelly_fraction": 0.25, "min_edge": 0.03}
        )
        self.active_strategies[core_genome.strategy_id] = StrategyState(
            genome=core_genome,
            status=StrategyStatus.ACTIVE,
            live_days=0,
            total_realized_ev=0.0,
            current_drawdown=0.0,
            decay_probability=0.0
        )
        logger.info(f"[APEL] Initialized Core Strategy: {core_genome.strategy_id}")

    def evaluate_portfolio_lifecycle(self, strategy_telemetry: Dict[str, Dict[str, float]]):
        """
        Evaluates all active strategies. Retires those that have died.
        Spawns new ones if capacity allows.
        
        strategy_telemetry: dict mapping strategy_id to metrics:
          - realized_ev: float
          - current_drawdown: float
          - decay_probability: float (from RegimeCompoundingDetector)
        """
        logger.info("================================================")
        logger.info("=== APEL PORTFOLIO EVOLUTION CYCLE ===")
        logger.info("================================================")
        
        retired_count = 0
        
        for strat_id, telemetry in strategy_telemetry.items():
            if strat_id not in self.active_strategies:
                continue
                
            state = self.active_strategies[strat_id]
            
            # Update state
            state.live_days += 1
            state.total_realized_ev += telemetry.get("realized_ev", 0.0)
            state.current_drawdown = telemetry.get("current_drawdown", state.current_drawdown)
            state.decay_probability = telemetry.get("decay_probability", state.decay_probability)
            
            # Check for Retirement
            if state.status in (StrategyStatus.ACTIVE, StrategyStatus.PROBATION):
                if state.decay_probability > self.RETIRE_DECAY_PROB or state.current_drawdown > self.RETIRE_MAX_DRAWDOWN:
                    logger.critical(f"[APEL] Strategy {strat_id} structurally failed! RETIRING.")
                    state.status = StrategyStatus.RETIRED
                    retired_count += 1
                elif state.decay_probability > 0.6 and state.status == StrategyStatus.ACTIVE:
                    logger.warning(f"[APEL] Strategy {strat_id} showing decay. Moving to PROBATION.")
                    state.status = StrategyStatus.PROBATION
                    
        # Remove retired strategies from the active pool
        active_ids = list(self.active_strategies.keys())
        for sid in active_ids:
            if self.active_strategies[sid].status == StrategyStatus.RETIRED:
                del self.active_strategies[sid]
                
        # Spawn new strategies if we have capacity
        current_active = len(self.active_strategies)
        if current_active < self.MAX_ACTIVE_STRATEGIES and retired_count > 0:
            self._spawn_new_variant()

    def _spawn_new_variant(self):
        """
        Generates a mutated variant of a successful strategy to replace a retired one.
        In a full implementation, this would trigger an AutoML retraining pipeline.
        """
        new_id = f"variant_{str(uuid.uuid4())[:8]}"
        new_genome = StrategyGenome(
            strategy_id=new_id,
            sport="NBA",
            market_type="PLAYER_PROPS",
            base_model_version="xgboost_v4.2_mutated",
            hyperparameters={"kelly_fraction": 0.15, "min_edge": 0.04} # More conservative
        )
        
        self.active_strategies[new_id] = StrategyState(
            genome=new_genome,
            status=StrategyStatus.ACTIVE,
            live_days=0,
            total_realized_ev=0.0,
            current_drawdown=0.0,
            decay_probability=0.0
        )
        logger.info(f"[APEL] Spawned new evolutionary variant: {new_id}")

    def get_active_strategies(self) -> List[str]:
        return list(self.active_strategies.keys())

apel_engine = AutonomousPortfolioEvolutionLayer()
