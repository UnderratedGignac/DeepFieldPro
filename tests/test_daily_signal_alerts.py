"""Tests for daily_signal_alerts.alert_new_picks() — one-time pick alerts
sized from the user's persistent real bankroll.

Guarantees under test (2026-07-13 rework):
  1. ONE alert per bet, ever — dedup is an INSERT OR IGNORE into a
     user_alerts table in bet_log.db, so it is atomic and immune to the
     twin-daemon race that made the old JSON-list dedup double-send.
  2. Suggested stake is sized from src.user_bankroll (persistent, carries
     across days) and the suggestion is auto-deducted so the next pick is
     sized from what's left.
  3. No balance reported -> alert still goes out, asking for the balance,
     and nothing is deducted.
"""

import sqlite3

import pytest

import src.daily_signal_alerts as dsa
import src.user_bankroll as ub


def _mk_bet_log(tmp_path, bets):
    db = str(tmp_path / "bet_log.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE bet_log (
            bet_id TEXT PRIMARY KEY, match_id TEXT, market_type TEXT,
            side TEXT, entry_odds REAL, stake REAL, fixture_id TEXT,
            bet_source TEXT, placed_at TEXT, result TEXT DEFAULT 'OPEN')"""
    )
    conn.executemany(
        "INSERT INTO bet_log (bet_id, match_id, market_type, side, entry_odds,"
        " stake, fixture_id, bet_source, placed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        bets,
    )
    conn.commit()
    conn.close()
    return db


def _bet(bid, match="Alpha vs Beta", side="Home (1)", odds=2.0, placed_at=None):
    return (
        bid, match, "1X2", side, odds, 5.0, "F1", "TIPSTER_FOREBET",
        placed_at or (dsa._today() + "T08:00:00"),
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = _mk_bet_log(tmp_path, [])
    monkeypatch.setattr(dsa, "BET_LOG", db)
    monkeypatch.setattr(dsa, "STATE_FILE", str(tmp_path / "daily_betting_state.json"))
    monkeypatch.setattr(ub, "STORE_FILE", str(tmp_path / "user_bankroll.json"))
    sent = []
    monkeypatch.setattr(dsa, "_ntfy", lambda title, body, **kw: sent.append((title, body)))
    # Confidence lookup goes to the network — stub it.
    monkeypatch.setattr(dsa, "_pick_confidence", lambda match: 60.0)
    return db, sent


def _add_bets(db, bets):
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO bet_log (bet_id, match_id, market_type, side, entry_odds,"
        " stake, fixture_id, bet_source, placed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        bets,
    )
    conn.commit()
    conn.close()


class TestOneTimeDelivery:
    def test_new_pick_alerts_once(self, env):
        db, sent = env
        _add_bets(db, [_bet("b1")])
        dsa.alert_new_picks()
        assert len(sent) == 1

    def test_second_run_does_not_resend(self, env):
        db, sent = env
        _add_bets(db, [_bet("b1")])
        dsa.alert_new_picks()
        dsa.alert_new_picks()
        assert len(sent) == 1

    def test_dedup_survives_wiped_json_state(self, env):
        """The old dedup lived only in daily_betting_state.json; when that
        file was lost/reset, every bet re-alerted. The DB-backed dedup must
        survive a wiped state file."""
        db, sent = env
        _add_bets(db, [_bet("b1")])
        dsa.alert_new_picks()
        import os
        os.remove(dsa.STATE_FILE) if os.path.exists(dsa.STATE_FILE) else None
        dsa.alert_new_picks()
        assert len(sent) == 1

    def test_user_alerts_table_records_send(self, env):
        db, sent = env
        _add_bets(db, [_bet("b1")])
        dsa.alert_new_picks()
        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT bet_id FROM user_alerts").fetchall()
        conn.close()
        assert rows == [("b1",)]


class TestStakeSuggestionAndAutoDeduct:
    def test_stake_sized_from_user_balance_and_deducted(self, env):
        db, sent = env
        ub.set_balance(100.0)
        _add_bets(db, [_bet("b1", odds=2.0)])
        dsa.alert_new_picks()
        assert len(sent) == 1
        body = sent[0][1]
        # p=0.60, odds=2.0 -> kelly=(0.6*2-1)/1=0.2; quarter=0.05 -> $5 of $100
        assert "$5.00" in body
        assert "$100.00" in body
        # Auto-deduct: next suggestion sizes from what's left.
        assert ub.get_balance() == 95.0

    def test_next_pick_sized_from_reduced_balance(self, env):
        db, sent = env
        ub.set_balance(100.0)
        _add_bets(db, [_bet("b1", odds=2.0)])
        dsa.alert_new_picks()
        _add_bets(db, [_bet("b2", match="Gamma vs Delta", odds=2.0)])
        dsa.alert_new_picks()
        body2 = sent[1][1]
        # Sized from $95, not $100: 95 * 0.05 = 4.75
        assert "$4.75" in body2
        assert "$95.00" in body2
        assert ub.get_balance() == pytest.approx(90.25)

    def test_no_balance_still_alerts_without_deducting(self, env):
        db, sent = env
        _add_bets(db, [_bet("b1")])
        dsa.alert_new_picks()
        assert len(sent) == 1
        assert "Reply with your balance" in sent[0][1]
        assert ub.get_balance() is None

    def test_zero_balance_does_not_suggest_a_stake(self, env):
        db, sent = env
        ub.set_balance(0.0)
        _add_bets(db, [_bet("b1")])
        dsa.alert_new_picks()
        assert len(sent) == 1
        assert "Balance is $0" in sent[0][1]
        assert ub.get_balance() == 0.0


class TestNationLeagueInAlert:
    """2026-07-13: the pick alert must carry nation + league so the user can
    find the exact match at their bookmaker (league from bet_log; nation
    resolved via the API-Football fixtures metadata)."""

    def _bet_with_league(self, bid, league):
        return (
            bid, "Alpha vs Beta", "1X2", "Home (1)", 2.0, 5.0, "F1",
            "TIPSTER_FOREBET", dsa._today() + "T08:00:00", league,
        )

    def _add_with_league(self, db, bets):
        conn = sqlite3.connect(db)
        conn.execute("ALTER TABLE bet_log ADD COLUMN league TEXT")
        conn.executemany(
            "INSERT INTO bet_log (bet_id, match_id, market_type, side, entry_odds,"
            " stake, fixture_id, bet_source, placed_at, league) VALUES (?,?,?,?,?,?,?,?,?,?)",
            bets,
        )
        conn.commit()
        conn.close()

    def test_alert_includes_nation_and_league(self, env, monkeypatch):
        db, sent = env
        self._add_with_league(db, [self._bet_with_league("n1", "Allsvenskan")])
        monkeypatch.setattr(dsa, "_nation_for", lambda match: "Sweden")
        dsa.alert_new_picks()
        assert len(sent) == 1
        assert "Sweden" in sent[0][1] and "Allsvenskan" in sent[0][1]

    def test_alert_falls_back_to_league_only(self, env, monkeypatch):
        db, sent = env
        self._add_with_league(db, [self._bet_with_league("n2", "FNL")])
        monkeypatch.setattr(dsa, "_nation_for", lambda match: None)
        dsa.alert_new_picks()
        assert len(sent) == 1
        assert "FNL" in sent[0][1]

    def test_alert_survives_bet_log_without_league_column(self, env, monkeypatch):
        db, sent = env
        _add_bets(db, [_bet("n3")])  # legacy schema, no league column
        monkeypatch.setattr(dsa, "_nation_for", lambda match: None)
        dsa.alert_new_picks()
        assert len(sent) == 1  # alert still goes out
