"""Staking-math tests.

Part 1 — log_ai_bet() in src/live_predictions_daemon.py:
    fractional-Kelly sizing (kelly_multiplier), the max_exposure_pct cap, the
    MAX_PAPER_STAKE_USD hard clamp, the $1 floor, the zero-stake shadow default,
    dedup/contradiction guards, and the SHADOW (no live order) gate.

Part 2 — src/bankroll_tracker.py:
    register_bet / register_settlement caps, exposure accounting, stop-loss HALT.

All DBs are tmp sqlite files, settings come from a tmp settings.json, and any
attempted network POST raises. No real data/*.db file is touched.
"""

import json
import sqlite3

import pytest
import requests as _requests_mod

from tests._daemon_test_utils import import_daemon

lpd = import_daemon()

import src.bankroll_tracker as bt  # noqa: E402


# ---------------------------------------------------------------------------
# Part 1: log_ai_bet
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "model_predictions_disabled": False,
    "tipster_only_mode": False,
    "ai_real_staking_enabled": True,
    "kelly_multiplier": 0.25,
    "max_exposure_pct": 0.05,
}


def _boom(*args, **kwargs):
    raise AssertionError("network POST attempted from a unit test")


@pytest.fixture
def ai_env(tmp_path, monkeypatch):
    """Sandboxed environment for log_ai_bet. Returns (data_dir, set_balance)."""
    data = tmp_path / "data"
    data.mkdir()

    conn = sqlite3.connect(data / "bet_log.db")
    conn.execute(
        """CREATE TABLE bet_log (
               bet_id TEXT PRIMARY KEY, match_id TEXT, player_id TEXT,
               market_type TEXT, entry_odds REAL, fair_odds REAL, edge_pct REAL,
               stake REAL, result TEXT DEFAULT 'OPEN', pnl REAL DEFAULT 0,
               placed_at TEXT, bet_source TEXT, is_recommended INTEGER DEFAULT 1,
               line TEXT, side TEXT, fixture_id TEXT, league TEXT)"""
    )
    conn.execute("CREATE TABLE stair_orders (bet_id TEXT, order_id TEXT)")
    conn.commit()
    conn.close()

    def set_balance(balance):
        c = sqlite3.connect(data / "bankroll.db")
        c.execute("CREATE TABLE IF NOT EXISTS bankroll (date TEXT, current_balance REAL)")
        c.execute("DELETE FROM bankroll")
        c.execute("INSERT INTO bankroll VALUES ('2026-07-10', ?)", (balance,))
        c.commit()
        c.close()

    def write_settings(**overrides):
        s = dict(DEFAULT_SETTINGS)
        s.update(overrides)
        (data / "settings.json").write_text(json.dumps(s))

    write_settings()
    set_balance(1000.0)

    monkeypatch.setattr(lpd, "DATA_DIR", str(data))
    monkeypatch.delenv("DEEPFIELD_DAEMON_LIVE_ORDERS", raising=False)
    # bankroll registration is Part 2's concern — accept everything here
    monkeypatch.setattr(bt, "register_bet", lambda stake, db_path=None: True)
    # any live order attempt must explode loudly
    monkeypatch.setattr(_requests_mod, "post", _boom)

    return data, set_balance, write_settings


def _stakes(data):
    conn = sqlite3.connect(data / "bet_log.db")
    rows = {
        r[0]: r[1]
        for r in conn.execute("SELECT match_id, stake FROM bet_log").fetchall()
    }
    conn.close()
    return rows


class TestLogAiBetKelly:
    def test_fractional_kelly_stake_below_cap(self, ai_env):
        data, _, _ = ai_env
        # p=0.55, odds=2.0 -> full kelly (p*o-1)/(o-1) = 0.10; quarter = 0.025
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=55.0, ev=0.10)
        assert _stakes(data)["A vs B"] == pytest.approx(1000.0 * 0.025)

    def test_max_exposure_pct_caps_kelly(self, ai_env):
        data, _, _ = ai_env
        # p=0.80, odds=2.0 -> full kelly 0.60; quarter 0.15 -> capped at 0.05
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=80.0, ev=0.60)
        assert _stakes(data)["A vs B"] == pytest.approx(1000.0 * 0.05)

    def test_max_paper_stake_hard_clamp(self, ai_env):
        data, set_balance, _ = ai_env
        set_balance(100000.0)
        # cap would be 5000; MAX_PAPER_STAKE_USD clamps to 200
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=80.0, ev=0.60)
        assert _stakes(data)["A vs B"] == pytest.approx(lpd.MAX_PAPER_STAKE_USD)
        assert lpd.MAX_PAPER_STAKE_USD == 200.0

    def test_negative_ev_floors_at_one_dollar(self, ai_env):
        """Real current behavior: kelly_f clamps to 0 for -EV picks, but the
        $1 minimum-stake floor then applies (stake is 1.0, not 0)."""
        data, _, _ = ai_env
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=40.0, ev=-0.20)
        assert _stakes(data)["A vs B"] == pytest.approx(1.0)

    def test_shadow_default_zero_stake_when_real_staking_disabled(self, ai_env):
        data, _, write_settings = ai_env
        write_settings(ai_real_staking_enabled=False)
        calls = []
        bt_orig = bt.register_bet
        try:
            bt.register_bet = lambda stake, db_path=None: (calls.append(stake), True)[1]
            lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=60.0, ev=0.20)
        finally:
            bt.register_bet = bt_orig
        assert _stakes(data)["A vs B"] == 0.0
        assert calls == []  # zero-stake bets never hit the bankroll tracker

    def test_gate_model_predictions_disabled_blocks_everything(self, ai_env):
        data, _, write_settings = ai_env
        write_settings(model_predictions_disabled=True)
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=60.0, ev=0.20)
        assert _stakes(data) == {}

    def test_implausible_odds_guard_blocks_bet(self, ai_env):
        data, _, _ = ai_env
        # 1X2 band is (1.01, 34.0)
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=50.0, prob=5.0, ev=0.50)
        assert _stakes(data) == {}

    def test_dedup_same_source_market_side(self, ai_env):
        data, _, _ = ai_env
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=55.0, ev=0.10)
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.1, prob=56.0, ev=0.12)
        conn = sqlite3.connect(data / "bet_log.db")
        (n,) = conn.execute("SELECT COUNT(*) FROM bet_log").fetchone()
        conn.close()
        assert n == 1

    def test_contradiction_guard_blocks_opposite_side_while_open(self, ai_env):
        data, _, _ = ai_env
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=55.0, ev=0.10)
        lpd.log_ai_bet("A vs B", "1X2", "Away", odds=3.5, prob=35.0, ev=0.10)
        conn = sqlite3.connect(data / "bet_log.db")
        (n,) = conn.execute("SELECT COUNT(*) FROM bet_log").fetchone()
        conn.close()
        assert n == 1

    def test_order_is_shadow_not_live(self, ai_env):
        """With DEEPFIELD_DAEMON_LIVE_ORDERS unset, the stair order id must be a
        SHADOW_ record and no HTTP POST may happen (requests.post raises here)."""
        data, _, _ = ai_env
        lpd.log_ai_bet("A vs B", "1X2", "Home", odds=2.0, prob=55.0, ev=0.10)
        conn = sqlite3.connect(data / "bet_log.db")
        (order_id,) = conn.execute("SELECT order_id FROM stair_orders").fetchone()
        conn.close()
        assert order_id.startswith("SHADOW_")

    def test_stake_property_never_exceeds_caps_never_negative(self, ai_env):
        """Property sweep: for any (prob, odds) the recorded stake obeys
        0 <= stake <= min(balance, MAX_PAPER_STAKE_USD) and
        stake <= max($1 floor, balance * max_exposure_pct)."""
        data, _, _ = ai_env
        balance, exposure_cap = 1000.0, 0.05
        i = 0
        for prob in (1.0, 20.0, 40.0, 52.0, 66.0, 80.0, 99.0):
            for odds in (1.05, 1.5, 2.0, 3.4, 10.0, 30.0):
                i += 1
                lpd.log_ai_bet(
                    f"Team{i} vs Other{i}", "1X2", "Home",
                    odds=odds, prob=prob, ev=0.10,
                )
        for match, stake in _stakes(data).items():
            assert stake >= 0.0, match
            assert stake <= min(balance, lpd.MAX_PAPER_STAKE_USD), match
            assert stake <= max(1.0, round(balance * exposure_cap, 2)), match


# ---------------------------------------------------------------------------
# Part 2: bankroll tracker caps
# ---------------------------------------------------------------------------

@pytest.fixture
def bankroll(tmp_path, monkeypatch):
    """Fresh $200 bankroll ledger in a tmp DB with known limits."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "max_daily_exposure_pct": 0.50,
                "max_drawdown_pct": 0.30,
                "daily_stop_loss_pct": 0.50,
                "stop_loss_enabled": True,
            }
        )
    )
    monkeypatch.setattr(bt, "_SETTINGS_PATH", str(settings))
    db = str(tmp_path / "bankroll.db")
    bt.init_bankroll_db(db)
    return db


def _status(db):
    return bt.get_status(db)


class TestBankrollTracker:
    def test_init_seeds_starting_bankroll(self, bankroll):
        s = _status(bankroll)
        assert s["current_balance"] == bt.STARTING_BANKROLL == 200.0
        assert s["status"] == "ACTIVE"
        assert s["daily_exposure"] == 0.0

    def test_register_bet_deducts_stake_and_books_exposure(self, bankroll):
        assert bt.register_bet(50.0, bankroll) is True
        s = _status(bankroll)
        assert s["current_balance"] == pytest.approx(150.0)
        assert s["daily_exposure"] == pytest.approx(50.0)

    def test_register_bet_blocks_stake_above_liquid_balance(self, bankroll):
        assert bt.register_bet(250.0, bankroll) is False
        assert _status(bankroll)["current_balance"] == pytest.approx(200.0)

    def test_register_bet_enforces_daily_exposure_cap(self, bankroll):
        # cap = 50% of 200 = $100 at risk at once
        assert bt.register_bet(60.0, bankroll) is True
        assert bt.register_bet(50.0, bankroll) is False  # 110 > 100
        s = _status(bankroll)
        assert s["daily_exposure"] == pytest.approx(60.0)
        assert s["current_balance"] == pytest.approx(140.0)

    def test_settlement_win_returns_payout_and_releases_exposure(self, bankroll):
        bt.register_bet(50.0, bankroll)
        # WIN at odds 2.5: payout 125, pnl 75
        bt.register_settlement(125.0, 75.0, bankroll)
        s = _status(bankroll)
        assert s["current_balance"] == pytest.approx(275.0)
        assert s["daily_exposure"] == pytest.approx(0.0)
        assert s["status"] == "ACTIVE"

    def test_settlement_void_is_a_full_refund(self, bankroll):
        bt.register_bet(50.0, bankroll)
        bt.register_settlement(50.0, 0.0, bankroll)  # VOID: payout=stake, pnl=0
        s = _status(bankroll)
        assert s["current_balance"] == pytest.approx(200.0)
        assert s["daily_exposure"] == pytest.approx(0.0)

    def test_big_loss_triggers_halt_and_blocks_new_bets(self, bankroll):
        assert bt.register_bet(100.0, bankroll) is True
        # LOSS: payout 0, pnl -100 -> drawdown 50% >= 30% limit -> HALT
        bt.register_settlement(0.0, -100.0, bankroll)
        s = _status(bankroll)
        assert s["status"] == "HALT"
        assert bt.register_bet(5.0, bankroll) is False

    def test_small_loss_stays_active(self, bankroll):
        bt.register_bet(20.0, bankroll)
        bt.register_settlement(0.0, -20.0, bankroll)  # 10% drawdown < 30%
        s = _status(bankroll)
        assert s["status"] == "ACTIVE"
        assert s["current_balance"] == pytest.approx(180.0)

    def test_stake_never_drives_balance_negative(self, bankroll):
        # sequence of maximal bets can never push liquid balance below zero
        while bt.register_bet(60.0, bankroll):
            pass
        assert _status(bankroll)["current_balance"] >= 0.0
