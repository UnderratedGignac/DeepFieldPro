"""Unit tests for Phase 3 (Paper vs Live Attribution) — src/attribution_engine.py."""

import pytest

from src import attribution_engine as attr


def _state(placed, settlements):
    return {"placed": placed, "settlements": settlements}


def test_empty_state_returns_valid_zero_report():
    report = attr.build_attribution_report(_state([], []))
    assert report["n_settled"] == 0
    assert report["scenarios"] == {}
    assert report["attribution"]["prediction"] is None
    assert "note" in report


def test_unsettled_bets_are_excluded():
    placed = [
        {"fixture_id": "F1", "ok": True, "outcome": "home", "staked_usd": 10.0,
         "limit_price": 0.6, "market_mid": 0.58, "edge_pp": 10.0, "model_prob": 0.68},
    ]
    report = attr.build_attribution_report(_state(placed, []))
    assert report["n_settled"] == 0


def test_failed_orders_excluded():
    placed = [
        {"fixture_id": "F1", "ok": False, "outcome": "home", "staked_usd": 10.0,
         "limit_price": 0.6, "market_mid": 0.58, "edge_pp": 10.0, "model_prob": 0.68},
    ]
    settlements = [{"fixture_id": "F1", "outcome": "home"}]
    report = attr.build_attribution_report(_state(placed, settlements))
    assert report["n_settled"] == 0


def test_winning_bet_pnl_and_scenarios():
    # $10 at limit 0.60 (mid 0.50), wins -> shares = 10/0.60 = 16.667,
    # payout = 16.667 - 10 = $6.67 actual; at mid 0.50: shares=20, payout=$10.
    placed = [
        {"fixture_id": "F1", "ok": True, "outcome": "home", "staked_usd": 10.0,
         "limit_price": 0.60, "market_mid": 0.50, "edge_pp": 15.0, "model_prob": 0.65},
    ]
    settlements = [{"fixture_id": "F1", "outcome": "home"}]
    report = attr.build_attribution_report(_state(placed, settlements))

    assert report["n_settled"] == 1
    assert report["scenarios"]["actual"]["total_pnl"] == pytest.approx(6.67, abs=0.01)
    assert report["scenarios"]["midpoint"]["total_pnl"] == pytest.approx(10.0, abs=0.01)
    # zero_fee identical to midpoint by construction (see docstring)
    assert report["scenarios"]["zero_fee"]["total_pnl"] == report["scenarios"]["midpoint"]["total_pnl"]
    # execution attribution: actual - midpoint (negative, since we paid the markup)
    assert report["attribution"]["execution"] == pytest.approx(-3.33, abs=0.01)
    assert report["attribution"]["fees"] == 0.0


def test_losing_bet_pnl_is_negative_stake():
    placed = [
        {"fixture_id": "F1", "ok": True, "outcome": "home", "staked_usd": 20.0,
         "limit_price": 0.60, "market_mid": 0.50, "edge_pp": 15.0, "model_prob": 0.65},
    ]
    settlements = [{"fixture_id": "F1", "outcome": "away"}]
    report = attr.build_attribution_report(_state(placed, settlements))
    assert report["scenarios"]["actual"]["total_pnl"] == -20.0
    assert report["scenarios"]["midpoint"]["total_pnl"] == -20.0  # loss is stake-size-invariant to price


def test_pure_kelly_sizing_attribution_uses_injected_kelly_fn():
    placed = [
        {"fixture_id": "F1", "ok": True, "outcome": "home", "staked_usd": 50.0,
         "limit_price": 0.60, "market_mid": 0.50, "edge_pp": 15.0, "model_prob": 0.65},
    ]
    settlements = [{"fixture_id": "F1", "outcome": "home"}]

    def fake_kelly(edge, mid, wallet_balance):
        return 5.0  # pretend pure Kelly would have staked far less than $50

    report = attr.build_attribution_report(_state(placed, settlements), kelly_fn=fake_kelly)
    # sizing = actual(at $50) - pure_kelly(at $5), both at limit_price -> large positive
    # gap here since production overstaked vs the Kelly formula
    assert report["attribution"]["sizing"] > 0


def test_calibration_proxy_reports_avg_prob_vs_win_rate():
    placed = [
        {"fixture_id": "F1", "ok": True, "outcome": "home", "staked_usd": 10.0,
         "limit_price": 0.6, "market_mid": 0.5, "edge_pp": 10.0, "model_prob": 0.80},
        {"fixture_id": "F2", "ok": True, "outcome": "away", "staked_usd": 10.0,
         "limit_price": 0.6, "market_mid": 0.5, "edge_pp": 10.0, "model_prob": 0.70},
    ]
    settlements = [
        {"fixture_id": "F1", "outcome": "draw"},  # lost
        {"fixture_id": "F2", "outcome": "away"},  # won
    ]
    report = attr.build_attribution_report(_state(placed, settlements))
    pred = report["attribution"]["prediction"]
    assert pred["avg_model_prob"] == pytest.approx(0.75)
    assert pred["realized_win_rate"] == pytest.approx(0.5)


def test_timing_attribution_is_none_not_fabricated():
    placed = [
        {"fixture_id": "F1", "ok": True, "outcome": "home", "staked_usd": 10.0,
         "limit_price": 0.6, "market_mid": 0.5, "edge_pp": 10.0, "model_prob": 0.65},
    ]
    settlements = [{"fixture_id": "F1", "outcome": "home"}]
    report = attr.build_attribution_report(_state(placed, settlements))
    assert report["attribution"]["timing"] is None
