"""
lgbm_predictor.py — LightGBM 1X2 predictor for real-time use in the daemon.

Loads the trained LightGBM model and provides predict_1x2() which takes the same
inputs as the DC model but returns sharper probabilities by combining DC + form + market.

Falls back gracefully to None if model not found or features unavailable.
"""

import json
import math
import os
import joblib

_MODEL = None
_FEATURES = None
_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "models", "lgbm_1x2.pkl"
)
_FEAT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "models", "lgbm_features.json"
)


def _load():
    global _MODEL, _FEATURES
    if _MODEL is not None:
        return True
    try:
        _MODEL = joblib.load(_MODEL_PATH)
        _FEATURES = json.load(open(_FEAT_PATH))["features"]
        return True
    except Exception:
        return False


def predict_1x2(
    dc_home_prob,
    dc_draw_prob,
    dc_away_prob,
    dc_exp_h,
    dc_exp_a,
    mkt_h_prob=None,
    mkt_d_prob=None,
    mkt_a_prob=None,
    home_form=None,
    away_form=None,
    h2h=None,
):
    """
    Returns (p_home, p_draw, p_away) using the LightGBM ensemble, or None if unavailable.

    home_form / away_form: dict with keys w5, d5, l5, gf5, ga5 (last-5 game counts).
    h2h: dict with keys home_w5, draw5, away_w5.
    Market probs default to 1/3 each if not provided (graceful degradation).
    """
    if not _load():
        return None

    # Default market to uniform if not available
    mkt_h = mkt_h_prob if mkt_h_prob is not None else 1 / 3
    mkt_d = mkt_d_prob if mkt_d_prob is not None else 1 / 3
    mkt_a = mkt_a_prob if mkt_a_prob is not None else 1 / 3

    hf = home_form or {}
    af = away_form or {}
    hh = h2h or {}

    row = [
        dc_home_prob,
        dc_draw_prob,
        dc_away_prob,
        dc_exp_h,
        dc_exp_a,
        mkt_h,
        mkt_d,
        mkt_a,
        hf.get("w5", 1.5),
        hf.get("d5", 1.5),
        hf.get("l5", 2.0),
        hf.get("gf5", 5.0),
        hf.get("ga5", 5.0),
        af.get("w5", 1.5),
        af.get("d5", 1.5),
        af.get("l5", 2.0),
        af.get("gf5", 5.0),
        af.get("ga5", 5.0),
        hh.get("home_w5", 1.0),
        hh.get("draw5", 1.0),
        hh.get("away_w5", 1.0),
    ]

    try:
        import pandas as pd

        df = pd.DataFrame([row], columns=_FEATURES)
        probs = _MODEL.predict_proba(df)[0]  # [p_H, p_D, p_A]
        return float(probs[0]), float(probs[1]), float(probs[2])
    except Exception:
        return None
