import sqlite3
import pandas as pd
import lightgbm as lgb
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def train_clv_meta_model(db_path: str = "data/bet_log.db"):
    """
    Trains a secondary model to predict the probability of a bet beating the closing line.
    Uses historical CLV data as ground truth.
    """
    if not os.path.exists(db_path):
        logger.error(f"Bet log DB not found at {db_path}")
        return None

    conn = sqlite3.connect(db_path)
    # Extract historical bets with CLV data
    query = """
    SELECT fair_prob, entry_odds, xmin_p10, xmin_p90, latency_ms, market_type, clv_percentage
    FROM bets
    WHERE clv_percentage IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if len(df) < 100:
        logger.warning("Insufficient data to train CLV meta-model.")
        return None

    # Target: 1 if we beat the closing line (CLV > 0), else 0
    df["is_sharp"] = (df["clv_percentage"] > 0).astype(int)

    # Features and Categorical handling
    df["market_type"] = df["market_type"].astype("category")
    features = [
        "fair_prob",
        "entry_odds",
        "xmin_p10",
        "xmin_p90",
        "latency_ms",
        "market_type",
    ]
    X = df[features]
    y = df["is_sharp"]

    # Train binary classifier
    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "boosting_type": "gbdt",
        "learning_rate": 0.05,
        "num_leaves": 15,
    }

    train_data = lgb.Dataset(X, label=y, categorical_feature=["market_type"])
    model = lgb.train(params, train_data, num_boost_round=200)

    logger.info("CLV Meta-Model trained successfully.")
    return model


def predict_market_acceptance(bet_proposal: Dict[str, Any], meta_model) -> float:
    """
    Returns a confidence score (0 to 1) indicating the probability
    that this bet will beat the closing line.
    """
    if meta_model is None:
        return 1.0  # Default to 1.0 if no model exists (passthrough)

    # Format proposal into dataframe
    proposal_df = pd.DataFrame(
        [
            {
                "fair_prob": bet_proposal.get("fair_prob"),
                "entry_odds": bet_proposal.get("entry_odds"),
                "xmin_p10": bet_proposal.get("xmin_p10"),
                "xmin_p90": bet_proposal.get("xmin_p90"),
                "latency_ms": bet_proposal.get("latency_ms", 0),
                "market_type": bet_proposal.get("market_type"),
            }
        ]
    )

    # Categorical handling
    proposal_df["market_type"] = proposal_df["market_type"].astype("category")

    # Predict probability of being 'sharp'
    confidence = meta_model.predict(proposal_df)[0]
    return float(confidence)


if __name__ == "__main__":
    # Example usage for training
    model = train_clv_meta_model()
    if model:
        # Save for inference
        import joblib

        joblib.dump(model, "models/clv_meta_model.pkl")
