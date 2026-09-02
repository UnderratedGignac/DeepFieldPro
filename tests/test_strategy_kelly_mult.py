"""Per-strategy Kelly multipliers must be configurable, not hardcoded.

`model_value_align_kelly_frac` sits in data/settings.json at 0.035 and appears
NOWHERE in the code — changing it does nothing. MODEL_VALUE_ALIGN's real sizing
came from a hardcoded boost inside log_ai_bet:

    if source == "MODEL_VALUE_ALIGN":
        mult = kelly_mult * 1.5      # 0.25 * 1.5 = 0.375
    elif source == "STAIR_AI":
        mult = kelly_mult * 1.2

That is why its bets were staking $5.00 (the stake_max clamp) against
PINNACLE_VALUE's $0.20-$0.25 — the strategy with the least trustworthy record
was betting 20-25x larger, sized off a virtual bankroll ($362.95) inflated by
settlement grades the 2026-08-24 analysis showed do not hold up.

_kelly_mult_for() makes the multiplier a real setting, defaulting to the exact
previous behaviour so nothing moves unless a value is set.
"""

import importlib

import pytest

lpd = importlib.import_module("src.live_predictions_daemon")

BASE = 0.25  # settings.kelly_multiplier default


# ---------------------------------------------------------------------------
# defaults preserve the old hardcoded behaviour
# ---------------------------------------------------------------------------


def test_model_value_align_default_matches_the_old_hardcoded_boost():
    assert lpd._kelly_mult_for("MODEL_VALUE_ALIGN", BASE, {}) == pytest.approx(0.375)


def test_stair_ai_default_matches_the_old_hardcoded_boost():
    assert lpd._kelly_mult_for("STAIR_AI", BASE, {}) == pytest.approx(0.30)


def test_other_sources_get_the_plain_multiplier():
    for src in ("AI", "PINNACLE_VALUE", "STEAM", None, ""):
        assert lpd._kelly_mult_for(src, BASE, {}) == pytest.approx(BASE)


# ---------------------------------------------------------------------------
# the setting now actually does something
# ---------------------------------------------------------------------------


def test_setting_overrides_the_model_value_align_default():
    got = lpd._kelly_mult_for(
        "MODEL_VALUE_ALIGN", BASE, {"model_value_align_kelly_frac": 0.02}
    )
    assert got == pytest.approx(0.02)


def test_setting_overrides_stair_ai():
    got = lpd._kelly_mult_for("STAIR_AI", BASE, {"stair_ai_kelly_frac": 0.05})
    assert got == pytest.approx(0.05)


def test_lowering_the_setting_lowers_the_multiplier():
    hi = lpd._kelly_mult_for("MODEL_VALUE_ALIGN", BASE, {})
    lo = lpd._kelly_mult_for(
        "MODEL_VALUE_ALIGN", BASE, {"model_value_align_kelly_frac": 0.02}
    )
    assert lo < hi


# ---------------------------------------------------------------------------
# robustness — a bad setting must never inflate a stake
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["abc", None, {}, []])
def test_unparseable_setting_falls_back_to_the_default(bad):
    got = lpd._kelly_mult_for(
        "MODEL_VALUE_ALIGN", BASE, {"model_value_align_kelly_frac": bad}
    )
    assert got == pytest.approx(0.375)


def test_negative_setting_is_clamped_to_zero_not_used_raw():
    got = lpd._kelly_mult_for(
        "MODEL_VALUE_ALIGN", BASE, {"model_value_align_kelly_frac": -1.0}
    )
    assert got == 0.0


def test_multiplier_is_capped_so_a_typo_cannot_blow_up_a_stake():
    """A fat-fingered 35 instead of 0.35 must not stake 100x."""
    got = lpd._kelly_mult_for(
        "MODEL_VALUE_ALIGN", BASE, {"model_value_align_kelly_frac": 35}
    )
    assert got <= 1.0


def test_settings_none_is_safe():
    assert lpd._kelly_mult_for("MODEL_VALUE_ALIGN", BASE, None) == pytest.approx(0.375)


# ---------------------------------------------------------------------------
# the live settings file must actually be wired now
# ---------------------------------------------------------------------------


def test_live_settings_value_is_honoured():
    """Regression guard for the dead-config bug: whatever is in settings.json
    for this key must change the multiplier."""
    import json
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "settings.json",
    )
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    if "model_value_align_kelly_frac" not in s:
        pytest.skip("key not present in settings.json")
    expected = min(1.0, max(0.0, float(s["model_value_align_kelly_frac"])))
    assert lpd._kelly_mult_for("MODEL_VALUE_ALIGN", BASE, s) == pytest.approx(expected)
