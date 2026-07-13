"""Tests for src/user_bankroll.py — the user's REAL-money balance tracker.

This is the phone-reported balance the user maintains by replying to ntfy
notifications with a number ("100" = $100). Unlike the old day-scoped
betarabia_balance in daily_betting_state.json, this balance PERSISTS across
days and is auto-decremented by each suggested stake, so the next pick's
suggestion is sized from what's actually left. The user can resync anytime
by sending a fresh number.
"""

import json

import pytest

import src.user_bankroll as ub


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "user_bankroll.json"
    monkeypatch.setattr(ub, "STORE_FILE", str(path))
    return path


class TestBalanceStore:
    def test_no_file_returns_none(self, store):
        assert ub.get_balance() is None

    def test_set_then_get_roundtrip(self, store):
        ub.set_balance(100)
        assert ub.get_balance() == 100.0

    def test_balance_persists_across_reload(self, store):
        """Not day-scoped: a balance saved yesterday is still the balance
        today (the old betarabia_balance reset to None at midnight UTC)."""
        ub.set_balance(87.5)
        raw = json.loads(store.read_text(encoding="utf-8"))
        assert raw["balance"] == 87.5
        # No date gate on read: whatever is stored is returned.
        assert ub.get_balance() == 87.5

    def test_deduct_reduces_balance(self, store):
        ub.set_balance(100)
        ub.deduct(12.5)
        assert ub.get_balance() == 87.5

    def test_deduct_never_goes_negative(self, store):
        ub.set_balance(5)
        ub.deduct(12.5)
        assert ub.get_balance() == 0.0

    def test_deduct_with_no_balance_is_noop(self, store):
        ub.deduct(10)
        assert ub.get_balance() is None

    def test_set_balance_records_history(self, store):
        ub.set_balance(100, source="user")
        ub.deduct(10, note="pick suggestion")
        raw = json.loads(store.read_text(encoding="utf-8"))
        assert len(raw["history"]) == 2
        assert raw["history"][0]["balance"] == 100.0
        assert raw["history"][0]["source"] == "user"
        assert raw["history"][1]["balance"] == 90.0
        assert raw["history"][1]["source"] == "deduct"

    def test_history_is_capped(self, store):
        ub.set_balance(1000)
        for _ in range(250):
            ub.deduct(1)
        raw = json.loads(store.read_text(encoding="utf-8"))
        assert len(raw["history"]) <= ub.HISTORY_CAP

    def test_invalid_amount_rejected(self, store):
        with pytest.raises(ValueError):
            ub.set_balance(-5)
        with pytest.raises(ValueError):
            ub.set_balance(float("nan"))
