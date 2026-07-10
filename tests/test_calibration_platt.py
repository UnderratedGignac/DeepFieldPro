"""Platt-calibration tests for _calibrate_1x2 / _calibrate_over25.

The calibrators load models/calibrator_1x2.json and calibrator_ou25.json
(read-only). Tests cover: output bounds [0, 100], identity fallbacks,
monotonicity, extreme inputs, a known-value identity transform (a=0, b=1),
and the dashboard's Under = 100 - Over complement rule.

NOTE: 1X2 calibration is applied per-outcome (marginal win prob), so the
calibrated H/D/A probabilities are NOT constrained to sum to 100 — that is
real, intended behavior and deliberately not asserted here.
"""

import pytest

from tests._daemon_test_utils import import_daemon

lpd = import_daemon()

GRID = [0.5, 1.0, 5.0, 10.0, 25.0, 38.0, 50.0, 62.5, 75.0, 90.0, 99.0, 99.5]


@pytest.fixture(params=["1x2", "ou25"])
def calibrate(request, monkeypatch):
    """Yield (fn, market) with the REAL model file force-reloaded from disk."""
    if request.param == "1x2":
        monkeypatch.setattr(lpd, "_CAL_1X2", None)  # force lazy reload
        return lpd._calibrate_1x2
    monkeypatch.setattr(lpd, "_CAL_OU", None)
    return lpd._calibrate_over25


class TestRealCalibrators:
    def test_output_stays_in_0_100(self, calibrate):
        for x in GRID:
            out = calibrate(x)
            assert 0.0 <= out <= 100.0, f"input {x} -> {out}"

    def test_monotonic_nondecreasing(self, calibrate):
        outs = [calibrate(x) for x in GRID]
        assert outs == sorted(outs)

    def test_extreme_inputs_do_not_crash_or_escape_bounds(self, calibrate):
        for x in (0.0, 100.0, 0.0001, 99.9999):
            out = calibrate(x)
            assert 0.0 <= out <= 100.0

    def test_output_rounded_to_one_decimal(self, calibrate):
        for x in GRID:
            out = calibrate(x)
            assert out == round(out, 1)


class TestIdentityFallbacks:
    def test_1x2_identity_when_no_calibrator(self, monkeypatch):
        monkeypatch.setattr(lpd, "_CAL_1X2", {})
        assert lpd._calibrate_1x2(66.0) == 66.0

    def test_1x2_identity_when_wrong_type(self, monkeypatch):
        monkeypatch.setattr(lpd, "_CAL_1X2", {"type": "isotonic", "a": 1, "b": 2})
        assert lpd._calibrate_1x2(42.0) == 42.0

    def test_ou_identity_when_no_calibrator(self, monkeypatch):
        monkeypatch.setattr(lpd, "_CAL_OU", {})
        assert lpd._calibrate_over25(51.3) == 51.3

    def test_platt_a0_b1_is_identity_transform(self, monkeypatch):
        """sigmoid(0 + 1*logit(p)) == p — sanity-checks the Platt formula."""
        monkeypatch.setattr(lpd, "_CAL_1X2", {"type": "platt", "a": 0.0, "b": 1.0})
        monkeypatch.setattr(lpd, "_CAL_OU", {"type": "platt", "a": 0.0, "b": 1.0})
        for x in (10.0, 30.0, 50.0, 62.5, 88.0):
            assert lpd._calibrate_1x2(x) == pytest.approx(x, abs=0.05)
            assert lpd._calibrate_over25(x) == pytest.approx(x, abs=0.05)

    def test_known_platt_value(self, monkeypatch):
        """Hand-computed: a=0, b=2 at p=0.5 -> logit 0 -> sigmoid(0)=0.5."""
        monkeypatch.setattr(lpd, "_CAL_1X2", {"type": "platt", "a": 0.0, "b": 2.0})
        assert lpd._calibrate_1x2(50.0) == pytest.approx(50.0)
        # a shifts the curve: a=ln(3), b=1 at p=0.5 -> sigmoid(ln 3)=0.75
        import math

        monkeypatch.setattr(
            lpd, "_CAL_1X2", {"type": "platt", "a": math.log(3.0), "b": 1.0}
        )
        assert lpd._calibrate_1x2(50.0) == pytest.approx(75.0)

    def test_extreme_coefficients_still_bounded(self, monkeypatch):
        monkeypatch.setattr(lpd, "_CAL_OU", {"type": "platt", "a": 50.0, "b": 10.0})
        for x in (0.0, 1.0, 50.0, 99.0, 100.0):
            out = lpd._calibrate_over25(x)
            assert 0.0 <= out <= 100.0


class TestUnderComplementRule:
    def test_under_is_100_minus_calibrated_over(self, monkeypatch):
        """The daemon derives Under as round(100 - _calibrate_over25(x), 1) so
        the displayed pair always sums to exactly 100 (complementary)."""
        monkeypatch.setattr(lpd, "_CAL_OU", None)  # real model file
        for x in GRID:
            over = lpd._calibrate_over25(x)
            under = round(100.0 - lpd._calibrate_over25(x), 1)
            assert 0.0 <= under <= 100.0
            assert over + under == pytest.approx(100.0, abs=1e-9)
