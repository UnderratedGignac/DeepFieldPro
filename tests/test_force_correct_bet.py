"""Tests for tools/force_correct_bet.py — the operator tool that re-grades a
single already-settled bet that was graded WRONG (the 2026-07-10 "River Plate
Reserves graded L instead of its real 4-0 home WIN" case).

The bet_log re-grade and the bankroll-ledger correction are separate functions so
an operator can fix the (unambiguous, safe) bet record without being forced to
mutate the real-money ledger in the same step.
"""
import sqlite3

import pytest

from src.settlement_provenance import ensure_settlement_provenance
from tools.force_correct_bet import (
    apply_ledger_correction,
    correct_bet,
    ledger_delta,
)

_SCHEMA = """
CREATE TABLE bet_log (
    bet_id TEXT PRIMARY KEY, match_id TEXT, market_type TEXT, side TEXT,
    entry_odds REAL, stake REAL, result TEXT DEFAULT 'OPEN', pnl REAL DEFAULT 0,
    bet_source TEXT
)
"""


@pytest.fixture()
def bet_db(tmp_path):
    p = str(tmp_path / "bet_log.db")
    conn = sqlite3.connect(p)
    conn.execute(_SCHEMA)
    conn.execute(
        "INSERT INTO bet_log (bet_id, match_id, market_type, side, entry_odds, stake, "
        "result, pnl, bet_source) VALUES "
        "('B','River Plate Reserves vs Racing Club Reserves','1X2','Home (1)',1.78,2,'L',-2,'TIPSTER_FOREBET')"
    )
    conn.commit()
    conn.close()
    ensure_settlement_provenance(p)  # install the trigger like the real DB
    return p


# ---- ledger_delta -----------------------------------------------------------

def test_ledger_delta_loss_to_win():
    # L (payout 0, pnl -2) -> W (payout 3.56, pnl +1.56): both deltas are +3.56.
    dp, dpnl = ledger_delta("L", "W", stake=2, odds=1.78)
    assert dp == pytest.approx(3.56)
    assert dpnl == pytest.approx(3.56)


def test_ledger_delta_win_to_loss_is_negative():
    dp, dpnl = ledger_delta("W", "L", stake=2, odds=1.78)
    assert dp == pytest.approx(-3.56)
    assert dpnl == pytest.approx(-3.56)


def test_ledger_delta_loss_to_void_refunds_stake_only():
    dp, dpnl = ledger_delta("L", "VOID", stake=2, odds=1.78)
    assert dp == pytest.approx(2.0)   # stake refunded
    assert dpnl == pytest.approx(2.0)  # -(-2)


# ---- correct_bet ------------------------------------------------------------

def test_correct_bet_flips_loss_to_win_with_provenance(bet_db):
    res = correct_bet(
        bet_db, "B", to_result="W",
        settle_source="operator-manual",
        settle_reason="verified 4-0 home win (Sofascore 2026-07-10)",
    )
    assert res["applied"] is True
    assert res["old_result"] == "L" and res["old_pnl"] == pytest.approx(-2)
    assert res["new_result"] == "W" and res["new_pnl"] == pytest.approx(1.56)

    conn = sqlite3.connect(bet_db)
    row = conn.execute(
        "SELECT result, pnl, settle_source, result_verified, settle_reason "
        "FROM bet_log WHERE bet_id='B'"
    ).fetchone()
    conn.close()
    assert row[0] == "W"
    assert row[1] == pytest.approx(1.56)
    assert row[2] == "operator-manual"
    assert row[3] == 1
    assert "4-0" in row[4]


def test_correct_bet_is_idempotent(bet_db):
    correct_bet(bet_db, "B", to_result="W", settle_source="op", settle_reason="r")
    again = correct_bet(bet_db, "B", to_result="W", settle_source="op", settle_reason="r")
    assert again["applied"] is False  # already W -> no-op
    conn = sqlite3.connect(bet_db)
    pnl = conn.execute("SELECT pnl FROM bet_log WHERE bet_id='B'").fetchone()[0]
    conn.close()
    assert pnl == pytest.approx(1.56)  # not doubled


def test_correct_bet_missing_bet_raises(bet_db):
    with pytest.raises(ValueError):
        correct_bet(bet_db, "NOPE", to_result="W", settle_source="op", settle_reason="r")


# ---- apply_ledger_correction (routing) --------------------------------------

def test_apply_ledger_correction_routes_forebet_to_real(monkeypatch):
    calls = []
    import src.bankroll_tracker as bt

    monkeypatch.setattr(
        bt, "register_settlement",
        lambda payout, pnl, db_path=None: calls.append((payout, pnl, db_path)),
    )
    apply_ledger_correction(
        3.56, 3.56, bet_source="TIPSTER_FOREBET",
        real_bankroll_db="/x/real_bankroll.db",
    )
    assert calls == [(pytest.approx(3.56), pytest.approx(3.56), "/x/real_bankroll.db")]


def test_apply_ledger_correction_routes_other_to_research(monkeypatch):
    calls = []
    import src.bankroll_tracker as bt

    monkeypatch.setattr(
        bt, "register_settlement",
        lambda payout, pnl, db_path=None: calls.append((payout, pnl, db_path)),
    )
    apply_ledger_correction(
        1.0, 1.0, bet_source="AI",
        real_bankroll_db="/x/real_bankroll.db",
        research_bankroll_db="/x/research_bankroll.db",
    )
    assert calls == [(pytest.approx(1.0), pytest.approx(1.0), "/x/research_bankroll.db")]
