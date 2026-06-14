import logging
import pandas as pd
from typing import Dict, Any

from src.research.policy_outcome_auditor.counterfactual_engine import (
    counterfactual_engine,
)
from src.research.policy_outcome_auditor.regret_engine import regret_engine
from src.research.policy_outcome_auditor.clv_validation_layer import clv_validator

logger = logging.getLogger(__name__)


class PolicyScoringSystem:
    """
    Phase 5: Policy Scoring System.
    Calculates aggregated scores and breakdowns across a batch of decisions.
    """

    def __init__(self):
        pass

    def score_batch(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Runs the full audit over a Pandas DataFrame of joined decisions/outcomes.
        """
        if df.empty:
            return {}

        total_decisions = len(df)
        total_regret = 0.0

        labels_count = {"CORRECT": 0, "OVER_CONSERVATIVE": 0, "OVER_AGGRESSIVE": 0}
        contradictions_count = {"MISSED": 0, "NEGATIVE_CLV": 0}

        for _, row in df.iterrows():
            row_dict = row.to_dict()

            # 1. Counterfactuals
            cfs = counterfactual_engine.compute_counterfactuals(row_dict)

            # 2. Regret
            regret_out = regret_engine.compute_regret(
                decision_action=row_dict.get("decision_action", "SKIP"),
                cf_execute_ev=cfs.execute_ev,
                cf_skip_ev=cfs.skip_ev,
            )

            total_regret += regret_out["regret_value"]
            if regret_out["label"] in labels_count:
                labels_count[regret_out["label"]] += 1

            # 3. CLV Contradictions
            clv_flag = clv_validator.evaluate_clv_contradiction(row_dict)
            if "MISSED_STRONG_CLV" in clv_flag:
                contradictions_count["MISSED"] += 1
            elif "EXECUTED_NEGATIVE_CLV" in clv_flag:
                contradictions_count["NEGATIVE_CLV"] += 1

        # Calculate final metrics
        regret_minimization_score = 1.0 - min(
            1.0, (total_regret / max(1, total_decisions))
        )
        accuracy = labels_count["CORRECT"] / total_decisions

        # The ultimate composite score
        # PolicyScore = weighted_accuracy + CLV_alignment + regret_minimization - overreaction_penalty
        policy_score = (
            (accuracy * 0.4)
            + (regret_minimization_score * 0.4)
            - ((contradictions_count["NEGATIVE_CLV"] / total_decisions) * 0.2)
        )

        logger.info(f"[POLICY SCORING] Evaluated {total_decisions} decisions.")
        logger.info(
            f"-> Accuracy: {accuracy*100:.1f}% | Total Regret: {total_regret:.3f}"
        )
        logger.info(
            f"-> Over-Conservative (Missed): {labels_count['OVER_CONSERVATIVE']}"
        )
        logger.info(f"-> Over-Aggressive (Bad Bets): {labels_count['OVER_AGGRESSIVE']}")
        logger.info(f"-> Final Policy Score: {policy_score:.3f}/1.000")

        return {
            "policy_score": round(policy_score, 3),
            "accuracy": round(accuracy, 3),
            "total_regret": round(total_regret, 4),
            "breakdown": labels_count,
        }


policy_scorer = PolicyScoringSystem()
