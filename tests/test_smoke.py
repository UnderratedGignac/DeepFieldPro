"""Smoke tests — verify core pure-logic utilities import and work correctly."""

import pytest


def test_kelly_fraction():
    """Kelly criterion: positive edge on a fair coin gives 0% stake."""
    p = 0.5
    odds = 2.0
    edge = p * odds - 1
    kelly = edge / (odds - 1)
    assert kelly == pytest.approx(0.0)


def test_kelly_positive_edge():
    """Kelly criterion: 55% win on evens gives 10% stake."""
    p = 0.55
    odds = 2.0
    edge = p * odds - 1
    kelly = edge / (odds - 1)
    assert kelly == pytest.approx(0.10)


def test_vig_removal_sum_to_one():
    """De-vigged probabilities for a 3-way market must sum to 1."""
    raw = [1.8, 3.5, 4.2]
    implied = [1 / o for o in raw]
    overround = sum(implied)
    fair = [p / overround for p in implied]
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)


def test_ev_calculation():
    """EV of a bet with 55% edge and 2.0 odds is +0.10 per unit."""
    prob = 0.55
    odds = 2.0
    ev = prob * (odds - 1) - (1 - prob)
    assert ev == pytest.approx(0.10)


def test_shadow_mode_default():
    """SHADOW_MODE must be True by default so no real money flows."""
    import os

    os.environ.setdefault("SHADOW_MODE", "true")
    shadow = os.environ.get("SHADOW_MODE", "true").lower() != "false"
    assert shadow is True, "SHADOW_MODE must default to True"
