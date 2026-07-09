"""Unit tests for Phase 5 (Edge Analysis) — src/edge_threshold_analysis.py."""

import random

import pytest

from src import edge_threshold_analysis as eta


def test_empty_returns_none_everywhere():
    m = eta.edge_threshold_metrics([])
    assert m["n"] == 0
    assert m["roi"] is None
    assert m["sharpe"] is None
    assert m["max_drawdown"] is None


def test_roi_and_hit_rate_basic():
    bets = [(True, 2.0), (False, 2.0), (True, 2.0), (False, 2.0)]  # even money, 50% hit
    m = eta.edge_threshold_metrics(bets)
    assert m["n"] == 4
    assert m["hit_rate"] == 0.5
    assert m["roi"] == pytest.approx(0.0, abs=1e-9)


def test_profitable_bets_positive_roi_and_profit_factor():
    # win pays 2:1 (price=3.0), 60% hit rate over many bets -> positive EV
    random.seed(0)
    bets = [(random.random() < 0.6, 3.0) for _ in range(500)]
    m = eta.edge_threshold_metrics(bets)
    assert m["roi"] > 0
    assert m["profit_factor"] > 1.0
    assert m["sharpe"] is not None


def test_max_drawdown_is_nonnegative_and_order_sensitive():
    # Same net P&L (0), different paths: A recovers to a small peak before a
    # 3-unit slide; B peaks immediately then slides 4 units straight down.
    recover_then_slide = [(False, 2.0), (True, 5.0), (False, 2.0), (False, 2.0), (False, 2.0)]
    peak_then_slide = [(True, 5.0), (False, 2.0), (False, 2.0), (False, 2.0), (False, 2.0)]
    dd_a = eta.edge_threshold_metrics(recover_then_slide)["max_drawdown"]
    dd_b = eta.edge_threshold_metrics(peak_then_slide)["max_drawdown"]
    assert dd_a >= 0
    assert dd_b >= 0
    assert dd_b > dd_a  # peaking immediately then sliding digs the deeper hole


def test_profit_factor_none_with_no_losses():
    bets = [(True, 2.0)] * 10
    returns = [(p - 1.0) for _, p in bets]
    assert eta.profit_factor(returns) is None


def test_kelly_growth_rate_positive_for_positive_edge():
    bets = [(True, 2.5)] * 100 + [(False, 2.5)] * 40  # ~71% hit at 1.5:1 -> +EV
    returns = [(p - 1.0) if w else -1.0 for w, p in bets]
    g = eta.kelly_growth_rate(returns, kelly_fraction=0.25)
    assert g > 0


def test_kelly_growth_rate_negative_for_negative_edge():
    bets = [(True, 1.5)] * 30 + [(False, 1.5)] * 70  # 30% hit at 0.5:1 -> -EV
    returns = [(p - 1.0) if w else -1.0 for w, p in bets]
    g = eta.kelly_growth_rate(returns, kelly_fraction=0.25)
    assert g < 0


def test_bootstrap_roi_ci_is_deterministic_with_seeded_rng():
    rng1 = random.Random(123)
    rng2 = random.Random(123)
    returns = [0.1, -1.0, 0.5, -1.0, 0.2, -1.0, 1.0]
    ci1 = eta.bootstrap_roi_ci(returns, n_resamples=200, rng=rng1)
    ci2 = eta.bootstrap_roi_ci(returns, n_resamples=200, rng=rng2)
    assert ci1 == ci2
    assert ci1[0] <= ci1[1]


def test_bootstrap_roi_ci_none_with_insufficient_data():
    assert eta.bootstrap_roi_ci([0.1]) is None
    assert eta.bootstrap_roi_ci([]) is None


def test_calmar_none_with_no_drawdown_or_empty():
    assert eta.calmar_ratio([]) is None
