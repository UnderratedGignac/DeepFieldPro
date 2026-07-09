"""Unit tests for Phase 10 (Adaptive Kelly) — src/adaptive_kelly.py."""

import pytest

from src import adaptive_kelly as ak


def test_calibration_score_perfect_and_capped():
    assert ak.calibration_score(0.0) == 1.0
    assert ak.calibration_score(0.15, ece_cap=0.15) == 0.0
    assert ak.calibration_score(0.30, ece_cap=0.15) == 0.0  # beyond cap, floors at 0
    assert ak.calibration_score(0.075, ece_cap=0.15) == pytest.approx(0.5)


def test_calibration_score_none_is_neutral_not_penalized():
    assert ak.calibration_score(None) == 1.0


def test_execution_score_penalizes_only_adverse_slippage():
    assert ak.execution_score(0.0) == 1.0
    assert ak.execution_score(0.025, slippage_cap=0.05) == pytest.approx(0.5)
    assert ak.execution_score(0.10, slippage_cap=0.05) == 0.0
    # Favorable (negative) slippage capped at 1.0, not rewarded above it.
    assert ak.execution_score(-0.05, slippage_cap=0.05) == 1.0


def test_execution_score_none_is_neutral():
    assert ak.execution_score(None) == 1.0


def test_liquidity_score_ratio_and_cap():
    # desired=$10, required_multiple=3 -> required=$30
    assert ak.liquidity_score(available_liquidity_usd=30.0, desired_usd=10.0, required_multiple=3) == 1.0
    assert ak.liquidity_score(available_liquidity_usd=15.0, desired_usd=10.0, required_multiple=3) == 0.5
    assert ak.liquidity_score(available_liquidity_usd=60.0, desired_usd=10.0, required_multiple=3) == 1.0  # capped
    assert ak.liquidity_score(available_liquidity_usd=0.0, desired_usd=10.0, required_multiple=3) == 0.0


def test_liquidity_score_neutral_when_nothing_being_sized():
    assert ak.liquidity_score(100.0, desired_usd=0.0, required_multiple=3) == 1.0
    assert ak.liquidity_score(100.0, desired_usd=None, required_multiple=3) == 1.0


def test_market_quality_score_vig_scaling():
    assert ak.market_quality_score(0.0) == 1.0
    assert ak.market_quality_score(5.0, vig_cap_pp=10.0) == pytest.approx(0.5)
    assert ak.market_quality_score(20.0, vig_cap_pp=10.0) == 0.0
    assert ak.market_quality_score(-2.0) == 1.0  # negative vig (loose market) capped at 1.0


def test_market_quality_score_none_is_neutral():
    assert ak.market_quality_score(None) == 1.0


def test_adaptive_kelly_multiplier_is_product_of_components():
    m = ak.adaptive_kelly_multiplier(calibration=0.8, execution=0.9, liquidity=1.0, market_quality=0.5)
    assert m == pytest.approx(0.8 * 0.9 * 1.0 * 0.5)


def test_adaptive_kelly_multiplier_all_neutral_is_one():
    assert ak.adaptive_kelly_multiplier(1.0, 1.0, 1.0, 1.0) == 1.0


def test_single_poor_component_meaningfully_shrinks_composite():
    good = ak.adaptive_kelly_multiplier(1.0, 1.0, 1.0, 1.0)
    one_poor = ak.adaptive_kelly_multiplier(1.0, 1.0, 1.0, 0.1)
    assert one_poor < good
    assert one_poor == pytest.approx(0.1)


def test_adaptive_kelly_size_scales_base_stake():
    size = ak.adaptive_kelly_size(50.0, calibration=1.0, execution=1.0, liquidity=1.0, market_quality=0.5)
    assert size == 25.0


def test_adaptive_kelly_size_with_all_neutral_equals_base():
    size = ak.adaptive_kelly_size(50.0, 1.0, 1.0, 1.0, 1.0)
    assert size == 50.0
