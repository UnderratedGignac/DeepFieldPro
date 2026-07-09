"""
Unit tests for Phase 1 risk-management changes in src/arena_betting.py:
- _wallet_kelly_size(): configurable kelly_fraction/min_usd/dd_multiplier
- _update_drawdown_state(): daily drawdown snapshot + tier lookup
- _directional_blocked(): arb-never-disabled bypass
- _directional_bet_size(): pure-Kelly sizing, no 40%-of-wallet floor

Pure-function tests, no live network calls, no Flask app context needed.
"""

import json

import pytest

from src import arena_betting as ab


# ---------------------------------------------------------------------------
# _wallet_kelly_size()
# ---------------------------------------------------------------------------
def test_wallet_kelly_size_default_matches_current_behavior():
    """No new kwargs -> same formula as the old hardcoded quarter-Kelly."""
    for edge, mid, bal in [(0.05, 0.40, 100.0), (0.10, 0.20, 250.0), (0.02, 0.60, 50.0)]:
        kelly_f = max(0.0, edge / (1.0 - mid))
        expected = round(max(1.00, min(kelly_f * 0.25 * bal, min(bal * 1.0, 100.00))), 2)
        assert ab._wallet_kelly_size(edge, mid, bal) == expected


def test_wallet_kelly_size_respects_kelly_fraction():
    edge, mid, bal = 0.10, 0.30, 200.0
    half = ab._wallet_kelly_size(edge, mid, bal, kelly_fraction=0.50, max_usd=1000, min_usd=0.0)
    tenth = ab._wallet_kelly_size(edge, mid, bal, kelly_fraction=0.10, max_usd=1000, min_usd=0.0)
    # Both sides are rounded to cents by _wallet_kelly_size, so allow a small
    # absolute tolerance rather than exact/relative equality.
    assert half == pytest.approx(tenth * 5, abs=0.02)


def test_wallet_kelly_size_respects_min_max():
    edge, mid, bal = 0.20, 0.10, 1000.0
    capped = ab._wallet_kelly_size(edge, mid, bal, kelly_fraction=1.0, max_usd=25.0, min_usd=1.0)
    assert capped <= 25.0

    floored = ab._wallet_kelly_size(0.001, 0.99, 10.0, kelly_fraction=0.25, max_usd=100.0, min_usd=7.5)
    assert floored == 7.5


def test_wallet_kelly_size_dd_multiplier_scales_down():
    edge, mid, bal = 0.15, 0.20, 500.0
    full = ab._wallet_kelly_size(edge, mid, bal, kelly_fraction=0.25, max_usd=1000, min_usd=0.0, dd_multiplier=1.0)
    half = ab._wallet_kelly_size(edge, mid, bal, kelly_fraction=0.25, max_usd=1000, min_usd=0.0, dd_multiplier=0.5)
    assert half == pytest.approx(full * 0.5, rel=1e-6)

    # Critical subtlety: dd_multiplier=0.0 does NOT zero the size — the
    # min_usd floor still applies. Disabling directional bets entirely must
    # happen via _directional_blocked() in autopilot_cycle(), not here.
    zeroed = ab._wallet_kelly_size(edge, mid, bal, kelly_fraction=0.25, max_usd=1000, min_usd=3.0, dd_multiplier=0.0)
    assert zeroed == 3.0


# ---------------------------------------------------------------------------
# _load_risk_settings() — backward compatibility
# ---------------------------------------------------------------------------
def test_load_risk_settings_falls_back_when_file_missing(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(ab, "_SETTINGS_PATH", str(missing))
    risk = ab._load_risk_settings()
    assert risk["kelly_fraction"] == 0.25
    assert risk["minimum_bet"] == ab.MIN_USD_PER_BET
    assert risk["maximum_bet"] == ab.MAX_USD_PER_BET
    assert risk["drawdown_protection_enabled"] is True
    assert risk["drawdown_tiers"][0]["drawdown_pct"] == 0.40  # sorted descending


def test_load_risk_settings_reads_configured_values(tmp_path, monkeypatch):
    cfg_path = tmp_path / "settings.json"
    cfg_path.write_text(
        json.dumps(
            {
                "arena_kelly_fraction": 0.5,
                "arena_minimum_bet": 2.0,
                "arena_maximum_bet": 50.0,
                "arena_drawdown_protection_enabled": False,
                "arena_drawdown_tiers": [
                    {"drawdown_pct": 0.05, "kelly_multiplier": 0.9, "disable_directional": False}
                ],
            }
        )
    )
    monkeypatch.setattr(ab, "_SETTINGS_PATH", str(cfg_path))
    risk = ab._load_risk_settings()
    assert risk["kelly_fraction"] == 0.5
    assert risk["minimum_bet"] == 2.0
    assert risk["maximum_bet"] == 50.0
    assert risk["drawdown_protection_enabled"] is False
    assert risk["drawdown_tiers"] == [{"drawdown_pct": 0.05, "kelly_multiplier": 0.9, "disable_directional": False}]


# ---------------------------------------------------------------------------
# _update_drawdown_state()
# ---------------------------------------------------------------------------
def _risk_cfg(enabled=True, tiers=None, forebet_required=True, arb_enabled=True):
    return {
        "kelly_fraction": 0.25,
        "minimum_bet": 1.0,
        "maximum_bet": 100.0,
        "drawdown_protection_enabled": enabled,
        "drawdown_tiers": tiers if tiers is not None else ab._DEFAULT_DRAWDOWN_TIERS,
        "forebet_required": forebet_required,
        "arb_enabled": arb_enabled,
    }


def test_update_drawdown_state_first_run_snapshots_and_returns_zero():
    state = {"daily": {"date": "2026-07-09", "spent": 0.0}}
    info = ab._update_drawdown_state(state, 113.18, _risk_cfg())
    assert state["daily"]["start_balance"] == 113.18
    assert info == {"drawdown_pct": 0.0, "kelly_multiplier": 1.0, "disable_directional": False}


@pytest.mark.parametrize(
    "drawdown_pct,expected_mult,expected_disable",
    [
        (0.00, 1.0, False),
        (0.05, 1.0, False),
        (0.0999, 1.0, False),   # just under 10% tier
        (0.10, 0.75, False),
        (0.15, 0.75, False),
        (0.20, 0.50, False),
        (0.25, 0.50, False),
        (0.30, 0.25, False),
        (0.35, 0.25, False),
        (0.40, 0.0, True),
        (0.60, 0.0, True),
    ],
)
def test_update_drawdown_state_tiers(drawdown_pct, expected_mult, expected_disable):
    start_balance = 100.0
    current_balance = start_balance * (1.0 - drawdown_pct)
    state = {"daily": {"date": "2026-07-09", "spent": 0.0, "start_balance": start_balance}}
    info = ab._update_drawdown_state(state, current_balance, _risk_cfg())
    assert info["kelly_multiplier"] == expected_mult
    assert info["disable_directional"] == expected_disable
    assert info["drawdown_pct"] == pytest.approx(drawdown_pct, abs=1e-6)


def test_update_drawdown_state_disabled_flag():
    state = {"daily": {"date": "2026-07-09", "spent": 0.0, "start_balance": 100.0}}
    info = ab._update_drawdown_state(state, 40.0, _risk_cfg(enabled=False))
    # Real drawdown (60%) still reported for visibility, but not enforced.
    assert info["drawdown_pct"] == pytest.approx(0.60)
    assert info["kelly_multiplier"] == 1.0
    assert info["disable_directional"] is False


def test_update_drawdown_state_zero_or_negative_start_balance():
    state = {"daily": {"date": "2026-07-09", "spent": 0.0, "start_balance": 0.0}}
    info = ab._update_drawdown_state(state, 5.0, _risk_cfg())
    assert info["drawdown_pct"] == 0.0
    assert info["kelly_multiplier"] == 1.0
    assert info["disable_directional"] is False

    state2 = {"daily": {"date": "2026-07-09", "spent": 0.0, "start_balance": -10.0}}
    info2 = ab._update_drawdown_state(state2, 5.0, _risk_cfg())
    assert info2["drawdown_pct"] == 0.0


# ---------------------------------------------------------------------------
# _directional_blocked() — "never disable arbitrage" is the load-bearing test
# ---------------------------------------------------------------------------
def test_directional_blocked_never_blocks_real_arb():
    dd_info = {"disable_directional": True}
    arb_pick = {"real_arb": True}
    directional_pick = {"real_arb": False}
    assert ab._directional_blocked(arb_pick, dd_info) is False
    assert ab._directional_blocked(directional_pick, dd_info) is True


def test_directional_blocked_no_effect_when_not_disabled():
    dd_info = {"disable_directional": False}
    assert ab._directional_blocked({"real_arb": False}, dd_info) is False
    assert ab._directional_blocked({"real_arb": True}, dd_info) is False


# ---------------------------------------------------------------------------
# _directional_bet_size() — no 40%-of-wallet floor remains
# ---------------------------------------------------------------------------
def test_directional_bet_size_no_forty_percent_floor():
    risk_cfg = _risk_cfg()
    # Low suggested_usd, high wallet_balance / room — a 40% floor would have
    # forced a much larger stake here; pure Kelly must not.
    size = ab._directional_bet_size(
        suggested_usd=2.50, risk_cfg=risk_cfg, max_per_bet=100.0, room=1000.0
    )
    assert size == 2.50


def test_directional_bet_size_respects_room_and_ceiling():
    risk_cfg = _risk_cfg()
    assert ab._directional_bet_size(50.0, risk_cfg, max_per_bet=20.0, room=1000.0) == 20.0
    assert ab._directional_bet_size(50.0, risk_cfg, max_per_bet=100.0, room=10.0) == 10.0
    # None suggested_usd falls back to configured minimum_bet.
    assert ab._directional_bet_size(None, risk_cfg, max_per_bet=100.0, room=1000.0) == risk_cfg["minimum_bet"]


# ---------------------------------------------------------------------------
# _forebet_gate_blocked() — Phase 13 configurable Forebet-required gate
# ---------------------------------------------------------------------------
def test_forebet_gate_default_matches_2026_07_06_behavior():
    risk_cfg = _risk_cfg()  # forebet_required=True, arb_enabled=True (defaults)
    tipster_confirmed = {"tipster_confirmed": True, "real_arb": False}
    real_arb_pick = {"tipster_confirmed": False, "real_arb": True}
    plain_pick = {"tipster_confirmed": False, "real_arb": False}
    assert ab._forebet_gate_blocked(tipster_confirmed, risk_cfg) is False
    assert ab._forebet_gate_blocked(real_arb_pick, risk_cfg) is False
    assert ab._forebet_gate_blocked(plain_pick, risk_cfg) is True


def test_forebet_gate_disabled_allows_all_qualifying_picks():
    risk_cfg = _risk_cfg(forebet_required=False)
    plain_pick = {"tipster_confirmed": False, "real_arb": False}
    assert ab._forebet_gate_blocked(plain_pick, risk_cfg) is False


def test_forebet_gate_arb_disabled_requires_forebet_even_for_arb():
    risk_cfg = _risk_cfg(arb_enabled=False)
    real_arb_pick = {"tipster_confirmed": False, "real_arb": True}
    assert ab._forebet_gate_blocked(real_arb_pick, risk_cfg) is True


# ---------------------------------------------------------------------------
# _load_risk_settings() — Phase 13 wc_model_weight
# ---------------------------------------------------------------------------
def test_load_risk_settings_wc_model_weight_default(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(ab, "_SETTINGS_PATH", str(missing))
    risk = ab._load_risk_settings()
    assert risk["wc_model_weight"] == ab.WC_MODEL_WEIGHT
    assert risk["forebet_required"] is True
    assert risk["arb_enabled"] is True


def test_load_risk_settings_wc_model_weight_configured(tmp_path, monkeypatch):
    cfg_path = tmp_path / "settings.json"
    cfg_path.write_text(json.dumps({"arena_wc_model_weight": 0.5, "arena_forebet_required": False}))
    monkeypatch.setattr(ab, "_SETTINGS_PATH", str(cfg_path))
    risk = ab._load_risk_settings()
    assert risk["wc_model_weight"] == 0.5
    assert risk["forebet_required"] is False
