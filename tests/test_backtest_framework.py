"""Unit tests for Phase 11 (Backtest Framework) — src/backtest_framework.py."""

import random

import pytest

from src import backtest_framework as bf


def test_monte_carlo_projection_none_on_empty_returns():
    assert bf.monte_carlo_projection([]) is None


def test_monte_carlo_projection_deterministic_with_seeded_rng():
    returns = [0.5, -1.0, 0.3, -1.0, 0.8]
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    proj1 = bf.monte_carlo_projection(returns, n_sims=200, rng=rng1)
    proj2 = bf.monte_carlo_projection(returns, n_sims=200, rng=rng2)
    assert proj1 == proj2


def test_monte_carlo_projection_positive_edge_grows_bankroll():
    random.seed(0)
    # Strong positive edge: 60% win at 2:1 -> should grow bankroll on average
    returns = [(2.0 if random.random() < 0.6 else -1.0) for _ in range(500)]
    proj = bf.monte_carlo_projection(returns, n_sims=1000, kelly_fraction=0.25, rng=random.Random(1))
    assert proj["median_ending_bankroll"] > 1.0
    assert proj["prob_of_ruin"] < 0.5


def test_monte_carlo_projection_negative_edge_shrinks_bankroll():
    random.seed(0)
    # Strong negative edge: 20% win at 1:1 -> should shrink bankroll
    returns = [(1.0 if random.random() < 0.2 else -1.0) for _ in range(500)]
    proj = bf.monte_carlo_projection(returns, n_sims=1000, kelly_fraction=0.25, rng=random.Random(1))
    assert proj["median_ending_bankroll"] < 1.0


def test_monte_carlo_bankroll_never_negative():
    returns = [-1.0] * 20  # every bet loses everything staked
    proj = bf.monte_carlo_projection(returns, n_sims=100, kelly_fraction=1.0, rng=random.Random(2))
    assert proj["median_ending_bankroll"] >= 0.0
    assert proj["p5_ending_bankroll"] >= 0.0


def test_full_backtest_report_empty_bets_is_valid_not_error():
    report = bf.full_backtest_report([])
    assert report["n"] == 0
    assert report["monte_carlo"] is None


def test_full_backtest_report_includes_all_phase5_metrics_plus_monte_carlo():
    random.seed(5)
    bets = [(random.random() < 0.55, 2.2) for _ in range(300)]
    report = bf.full_backtest_report(bets, n_sims=500, rng=random.Random(3))
    for key in ("n", "roi", "hit_rate", "sharpe", "sortino", "max_drawdown", "calmar", "profit_factor", "kelly_growth", "roi_ci_95"):
        assert key in report
    assert report["monte_carlo"] is not None
    assert "median_ending_bankroll" in report["monte_carlo"]
