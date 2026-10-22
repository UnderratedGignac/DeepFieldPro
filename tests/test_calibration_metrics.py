"""Unit tests for Phase 4 (Model Calibration) — src/calibration_metrics.py."""

import random

import pytest

from src import calibration_metrics as cal


def test_empty_input_returns_none_not_error():
    assert cal.brier_score([], []) is None
    assert cal.log_loss([], []) is None
    assert cal.reliability_bins([], []) == []
    assert cal.expected_calibration_error([], []) is None
    assert cal.max_calibration_error([], []) is None
    summary = cal.calibration_summary([], [])
    assert summary["n"] == 0
    assert summary["brier_score"] is None


def test_perfect_predictions_have_zero_brier_and_log_loss():
    probs = [1.0 - 1e-9] * 5 + [1e-9] * 5
    outcomes = [1] * 5 + [0] * 5
    assert cal.brier_score(probs, outcomes) == pytest.approx(0.0, abs=1e-6)
    assert cal.log_loss(probs, outcomes) == pytest.approx(0.0, abs=1e-4)


def test_well_calibrated_synthetic_data_has_low_ece():
    """Generate outcomes that literally match their stated probabilities on
    average, at coarse probability levels — ECE should be near zero."""
    random.seed(42)
    probs, outcomes = [], []
    for p in (0.2, 0.4, 0.6, 0.8):
        for _ in range(500):
            probs.append(p)
            outcomes.append(1 if random.random() < p else 0)
    ece = cal.expected_calibration_error(probs, outcomes, n_bins=10)
    assert ece < 0.05  # well-calibrated by construction, allow sampling noise


def test_badly_miscalibrated_data_has_high_ece_and_mce():
    """Model always says 90% confident but is only right half the time."""
    random.seed(7)
    probs = [0.9] * 1000
    outcomes = [1 if random.random() < 0.5 else 0 for _ in range(1000)]
    ece = cal.expected_calibration_error(probs, outcomes, n_bins=10)
    mce = cal.max_calibration_error(probs, outcomes, n_bins=10)
    assert ece > 0.3
    assert mce > 0.3


def test_reliability_bins_shape_and_coverage():
    probs = [0.1, 0.15, 0.5, 0.55, 0.9, 0.95]
    outcomes = [0, 0, 1, 0, 1, 1]
    bins = cal.reliability_bins(probs, outcomes, n_bins=10)
    assert sum(b["n"] for b in bins) == len(probs)
    for b in bins:
        assert b["bin_lo"] < b["bin_hi"]
        assert 0.0 <= b["avg_predicted"] <= 1.0
        assert 0.0 <= b["avg_actual"] <= 1.0


# ---------------------------------------------------------------------------
# Rescaling
# ---------------------------------------------------------------------------
def test_fit_platt_scaling_improves_overconfident_predictions():
    random.seed(1)
    # True win probability is 0.5 regardless of the (overconfident) stated prob.
    probs = [0.9 if i % 2 == 0 else 0.1 for i in range(2000)]
    outcomes = [1 if random.random() < 0.5 else 0 for _ in range(2000)]
    before = cal.log_loss(probs, outcomes)
    scaler = cal.fit_platt_scaling(probs, outcomes)
    assert scaler is not None
    scaled = scaler(probs)
    after = cal.log_loss(scaled, outcomes)
    assert after <= before


def test_fit_isotonic_scaling_returns_monotonic_callable():
    random.seed(2)
    probs = sorted([random.random() for _ in range(500)])
    outcomes = [1 if p > 0.5 else 0 for p in probs]
    scaler = cal.fit_isotonic_scaling(probs, outcomes)
    assert scaler is not None
    scaled = scaler(probs)
    # monotonic non-decreasing in the sorted-input order
    assert all(scaled[i] <= scaled[i + 1] + 1e-9 for i in range(len(scaled) - 1))


def test_fit_temperature_scaling_finds_reasonable_temperature():
    random.seed(3)
    probs = [0.9 if i % 2 == 0 else 0.1 for i in range(2000)]
    outcomes = [1 if random.random() < 0.5 else 0 for _ in range(2000)]
    scaler = cal.fit_temperature_scaling(probs, outcomes)
    assert scaler is not None
    # Overconfident (0.9/0.1 when truth is 50/50) should need T > 1 to soften.
    assert scaler.temperature > 1.0
    scaled = scaler(probs)
    assert all(0.0 <= s <= 1.0 for s in scaled)


def test_scalers_return_none_with_insufficient_data():
    assert cal.fit_platt_scaling([0.5], [1]) is None  # single class
    assert cal.fit_isotonic_scaling([], []) is None
    assert cal.fit_temperature_scaling([0.5, 0.6], [1, 1]) is None  # single class
