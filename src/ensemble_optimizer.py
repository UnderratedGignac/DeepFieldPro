"""
ensemble_optimizer.py — Phase 8 (Ensemble Optimization) for DeepFieldPro.

Pure, testable functions for combining two probability sources (a model and
the de-vigged market — this project's own actual ensemble members, per
data/settings.json's `market_blend_weight` and src/arena_betting.py's
`WC_MODEL_WEIGHT`) and scoring the result. The walk-forward glue (loading
data/history.db, fitting Dixon-Coles per league/season, sweeping blend
weights, fitting a logistic-stacking model) lives in
tools/ensemble_optimization_report.py, mirroring the existing
tools/backtest_1x2_lines.py structure (testable core + a CLI orchestrator).

Scope note: this evaluates MODEL-vs-MARKET blending (the ensemble this
project actually uses in two places today, at two different hardcoded
weights: 0.5 in the paper daemon, 0.65 in Arena) using data/history.db, which
has real market odds to blend against. A true Elo-vs-Dixon-Coles blend
specifically for World Cup matches would need enough SETTLED Arena bets to
validate — there are currently zero (see attribution_engine.py) — so that
comparison isn't fabricated here; it's noted as a data-availability gap in
the CLI's output instead.
"""

import math


def blend_probs(model_probs, market_probs, weight):
    """
    weight=1.0 -> pure model, weight=0.0 -> pure market, linear in between.
    Renormalized to sum to 1 (guards against either input not already
    summing to exactly 1.0 due to rounding). Missing outcomes are treated as
    probability 0 in that source.
    """
    out = {}
    for k in ("home", "draw", "away"):
        out[k] = weight * model_probs.get(k, 0.0) + (1.0 - weight) * market_probs.get(k, 0.0)
    total = sum(out.values())
    if total <= 0:
        return out
    return {k: v / total for k, v in out.items()}


def multiclass_log_loss(prob_dicts, actual_outcomes, eps=1e-12):
    """
    Mean multiclass log loss: -mean(log(p[actual])). `prob_dicts` is a list
    of {"home":p,"draw":p,"away":p}; `actual_outcomes` is a parallel list of
    "home"/"draw"/"away" strings. None if the lists are empty/mismatched.
    """
    if not prob_dicts or len(prob_dicts) != len(actual_outcomes):
        return None
    total = 0.0
    for probs, actual in zip(prob_dicts, actual_outcomes):
        p = max(eps, min(1 - eps, probs.get(actual, 0.0)))
        total += -math.log(p)
    return total / len(prob_dicts)


def multiclass_brier(prob_dicts, actual_outcomes):
    """
    Mean multiclass Brier score: mean(sum_k (p_k - y_k)^2) over the 3
    outcomes. Lower is better (0 = perfect). None if lists are empty/mismatched.
    """
    if not prob_dicts or len(prob_dicts) != len(actual_outcomes):
        return None
    total = 0.0
    for probs, actual in zip(prob_dicts, actual_outcomes):
        for k in ("home", "draw", "away"):
            y = 1.0 if k == actual else 0.0
            total += (probs.get(k, 0.0) - y) ** 2
    return total / len(prob_dicts)


def best_ev_pick(prob_dict, odds_dict, ev_threshold=0.0):
    """
    Pick the outcome with the highest expected value (prob*odds - 1) among
    the 3 outcomes, if it clears `ev_threshold`. Returns (outcome, ev) or
    (None, None) if no outcome clears the threshold or inputs are incomplete.
    """
    best_outcome, best_ev = None, None
    for k in ("home", "draw", "away"):
        p = prob_dict.get(k)
        o = odds_dict.get(k)
        if p is None or not o:
            continue
        ev = p * o - 1.0
        if best_ev is None or ev > best_ev:
            best_outcome, best_ev = k, ev
    if best_ev is not None and best_ev >= ev_threshold:
        return best_outcome, best_ev
    return None, None
