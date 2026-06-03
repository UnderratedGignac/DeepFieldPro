import logging
from typing import Dict, Any

from src.research.meta_governor.meta_regret_engine import meta_regret_engine
from src.research.meta_governor.system_health_scorer import health_scorer
from src.research.meta_governor.learning_rate_controller import lr_controller
from src.research.meta_governor.global_safety_constraints import safety_constraints

logger = logging.getLogger(__name__)


class MetaGovernorLayer:
    """
    The MGL Engine.
    Governs ALL lower layers (POA, APO, SCG) to ensure the adaptive system
    improves realized performance without collapsing into self-referential loops.
    """

    def __init__(self):
        pass

    def evaluate_and_control(
        self, mgl_inputs: Dict[str, Any], apo_proposal: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        The Runtime Execution Flow.
        1. POA produces regret signals (Inferred via mgl_inputs)
        2. APO proposes updates (apo_proposal)
        3. MGL evaluates system health
        4. MGL modifies learning rate / update permissions
        5. Final safe update applied (or rejected)
        """
        logger.info("================================================")
        logger.info("=== META-GOVERNOR LAYER (MGL) EVALUATION ===")
        logger.info("================================================")

        # 1. Compute Meta-Regret from actual inputs
        # Build rolling decisions from the ingested mgl_inputs signal
        rolling_decisions = mgl_inputs.get(
            "rolling_decisions",
            [
                {
                    "baseline_realized_ev": mgl_inputs.get("baseline_ev", 0.0),
                    "adaptive_realized_ev": mgl_inputs.get("adaptive_ev", 0.0),
                }
            ],
        )
        meta_metrics = meta_regret_engine.compute_meta_regret(rolling_decisions)
        logger.info(
            f"[MGL] Meta-Regret: {meta_metrics.meta_regret:.2f} (Adaptive system underperforming baseline)"
        )

        # 2. Evaluate System Health
        health = health_scorer.evaluate_health(
            realized_ev_trend=mgl_inputs.get("realized_ev_trend", -0.05),
            clv_stability=mgl_inputs.get("clv_stability", 0.9),
            current_drawdown=mgl_inputs.get("current_drawdown", 0.05),
            meta_regret=meta_metrics.meta_regret,
        )

        # 3. Modify Learning Rate
        dynamic_lr = lr_controller.compute_learning_rate(
            health, meta_metrics.meta_regret
        )
        logger.info(f"[MGL] Permitted Learning Rate: {dynamic_lr:.3f}")

        if dynamic_lr == 0.0:
            return {
                "status": "REJECTED_FROZEN",
                "reason": "System Collapsing. Learning Frozen.",
            }

        # 4. Enforce Global Safety Constraints on APO Proposal
        proposed_ev = apo_proposal.get("proposed_min_ev")
        current_ev = apo_proposal.get("current_min_ev")

        # BUG FIX: Guard against None values crashing abs() in safety_constraints
        if proposed_ev is None or current_ev is None:
            return {
                "status": "REJECTED_MISSING_PARAMS",
                "reason": "APO proposal missing proposed_min_ev or current_min_ev.",
            }

        is_safe = safety_constraints.validate_apo_update(proposed_ev, current_ev)

        if not is_safe:
            return {
                "status": "REJECTED_UNSAFE",
                "reason": "APO Proposal violated global safety bounds.",
            }

        # BUG FIX: LR scaling was dividing by base_lr constant (0.05) making it
        # fragile if base_lr ever changes. Now uses the actual base_lr from controller.
        base_lr = lr_controller.base_lr
        lr_ratio = dynamic_lr / base_lr if base_lr > 0 else 0.0
        delta = (proposed_ev - current_ev) * lr_ratio
        final_ev = current_ev + delta

        logger.info(
            f"[MGL] Update APPROVED and DAMPED. EV Threshold: {current_ev:.3f} -> {final_ev:.3f}"
        )

        return {"status": "APPROVED", "final_min_ev": round(final_ev, 3)}


mgl_engine = MetaGovernorLayer()
