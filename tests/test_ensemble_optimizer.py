"""Unit tests for Phase 8 (Ensemble Optimization) — src/ensemble_optimizer.py."""

import pytest

from src import ensemble_optimizer as eo


def test_blend_probs_pure_model_and_pure_market():
    model = {"home": 0.6, "draw": 0.2, "away": 0.2}
    market = {"home": 0.4, "draw": 0.3, "away": 0.3}
    assert eo.blend_probs(model, market, weight=1.0) == pytest.approx(model)
    assert eo.blend_probs(model, market, weight=0.0) == pytest.approx(market)


def test_blend_probs_midpoint():
    model = {"home": 0.6, "draw": 0.2, "away": 0.2}
    market = {"home": 0.4, "draw": 0.3, "away": 0.3}
    blended = eo.blend_probs(model, market, weight=0.5)
    assert blended["home"] == pytest.approx(0.5)
    assert blended["draw"] == pytest.approx(0.25)
    assert blended["away"] == pytest.approx(0.25)
    assert sum(blended.values()) == pytest.approx(1.0)


def test_blend_probs_renormalizes_when_inputs_dont_sum_to_one():
    model = {"home": 0.5, "draw": 0.3, "away": 0.3}  # sums to 1.1
    market = {"home": 0.3, "draw": 0.3, "away": 0.3}  # sums to 0.9
    blended = eo.blend_probs(model, market, weight=0.5)
    assert sum(blended.values()) == pytest.approx(1.0)


def test_multiclass_log_loss_perfect_predictions_near_zero():
    probs = [{"home": 1 - 1e-9, "draw": 5e-10, "away": 5e-10}] * 5
    actual = ["home"] * 5
    assert eo.multiclass_log_loss(probs, actual) == pytest.approx(0.0, abs=1e-6)


def test_multiclass_log_loss_empty_or_mismatched_returns_none():
    assert eo.multiclass_log_loss([], []) is None
    assert eo.multiclass_log_loss([{"home": 1.0}], []) is None


def test_multiclass_brier_perfect_vs_worst_case():
    perfect = [{"home": 1.0, "draw": 0.0, "away": 0.0}]
    worst = [{"home": 0.0, "draw": 0.0, "away": 1.0}]
    actual = ["home"]
    assert eo.multiclass_brier(perfect, actual) == pytest.approx(0.0)
    # worst case: predicted away=1 but actual home -> (0-1)^2 + 0 + (1-0)^2 = 2
    assert eo.multiclass_brier(worst, actual) == pytest.approx(2.0)


def test_best_ev_pick_selects_highest_ev_above_threshold():
    probs = {"home": 0.5, "draw": 0.3, "away": 0.2}
    odds = {"home": 1.8, "draw": 3.5, "away": 5.0}
    # EVs: home = 0.5*1.8-1=-0.1, draw=0.3*3.5-1=0.05, away=0.2*5-1=0.0
    outcome, ev = eo.best_ev_pick(probs, odds, ev_threshold=0.0)
    assert outcome == "draw"
    assert ev == pytest.approx(0.05)


def test_best_ev_pick_returns_none_when_no_outcome_clears_threshold():
    probs = {"home": 0.3, "draw": 0.3, "away": 0.3}
    odds = {"home": 2.0, "draw": 2.0, "away": 2.0}  # all EV = -0.4
    outcome, ev = eo.best_ev_pick(probs, odds, ev_threshold=0.0)
    assert outcome is None
    assert ev is None


def test_best_ev_pick_handles_missing_odds_gracefully():
    probs = {"home": 0.5, "draw": 0.3, "away": 0.2}
    odds = {"home": 1.8}  # draw/away odds missing
    outcome, ev = eo.best_ev_pick(probs, odds, ev_threshold=-1.0)
    assert outcome == "home"
