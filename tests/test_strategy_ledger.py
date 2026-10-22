"""Per-strategy virtual bankrolls (2026-07-14): each strategy gets its own
ledger COMPUTED from bet_log ground truth (starting capital + settled pnl −
open stakes) — no new mutating ledger files, so per-strategy accounting can
never drift from the bet record the way the physical ledgers did."""
import sqlite3

import pytest

from src.strategy_ledger import strategy_ledgers

_SCHEMA = """
CREATE TABLE bet_log (
    bet_id TEXT PRIMARY KEY, match_id TEXT, market_type TEXT, side TEXT,
    entry_odds REAL, stake REAL, result TEXT DEFAULT 'OPEN', pnl REAL DEFAULT 0,
    bet_source TEXT, placed_at TEXT
)
"""


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "bet_log.db")
    conn = sqlite3.connect(p)
    conn.execute(_SCHEMA)
    rows = [
        ("f1", "TIPSTER_FOREBET", "W", 2.0, 3.0, "2026-07-13T10:00:00"),   # won +3
        ("f2", "TIPSTER_FOREBET", "L", 5.0, -5.0, "2026-07-13T11:00:00"),  # lost -5
        ("f3", "TIPSTER_FOREBET", "OPEN", 4.0, 0.0, "2026-07-14T05:00:00"),
        ("s1", "STEAM", "W", 1.0, 1.5, "2026-07-13T09:00:00"),
        ("s2", "STEAM_LL", "OPEN", 1.0, 0.0, "2026-07-14T06:00:00"),
        ("v1", "TIPSTER_FOREBET", "VOID", 2.0, 0.0, "2026-07-12T08:00:00"),
    ]
    for bid, src, res, stake, pnl, d in rows:
        conn.execute(
            "INSERT INTO bet_log (bet_id, match_id, market_type, side, entry_odds,"
            " stake, result, pnl, bet_source, placed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (bid, "A vs B", "1X2", "Home (1)", 2.0, stake, res, pnl, src, d),
        )
    conn.commit()
    conn.close()
    return p


def test_ledger_per_strategy_computed_from_bet_log(db):
    led = strategy_ledgers(db, starting=100.0)
    fb = led["TIPSTER_FOREBET"]
    assert fb["settled_pnl"] == pytest.approx(-2.0)   # +3 - 5 (VOID = 0)
    assert fb["open_stake"] == pytest.approx(4.0)
    assert fb["balance"] == pytest.approx(94.0)       # 100 - 2 - 4 at risk
    assert fb["total_value"] == pytest.approx(98.0)   # balance + at-risk
    assert fb["n_settled"] == 2 and fb["n_open"] == 1

    st = led["STEAM"]
    assert st["balance"] == pytest.approx(101.5)
    assert led["STEAM_LL"]["open_stake"] == pytest.approx(1.0)


def test_strategies_are_isolated(db):
    led = strategy_ledgers(db, starting=100.0)
    # One strategy's losses never touch another's ledger.
    assert led["STEAM"]["settled_pnl"] == pytest.approx(1.5)
    assert led["TIPSTER_FOREBET"]["settled_pnl"] == pytest.approx(-2.0)


def test_empty_db_returns_empty(tmp_path):
    p = str(tmp_path / "empty.db")
    conn = sqlite3.connect(p)
    conn.execute(_SCHEMA)
    conn.close()
    assert strategy_ledgers(p) == {}


class TestLedgerReset:
    """Reset-to-$100 (2026-07-14): ledgers are computed, so a reset is an
    EPOCH marker — only bets placed at/after it count. History stays in
    bet_log untouched; the bankroll simply restarts from $100."""

    def test_reset_epoch_excludes_prior_bets(self, db, tmp_path):
        from src import strategy_ledger as sl
        epoch_file = str(tmp_path / "epoch.json")
        sl.reset_strategy_ledgers(when="2026-07-14T00:00:00", epoch_file=epoch_file)
        led = sl.strategy_ledgers(db, starting=100.0, epoch_file=epoch_file)
        fb = led["TIPSTER_FOREBET"]
        # Only the 2026-07-14 OPEN bet survives the epoch; settled history gone.
        assert fb["settled_pnl"] == pytest.approx(0.0)
        assert fb["open_stake"] == pytest.approx(4.0)
        assert fb["balance"] == pytest.approx(96.0)
        assert fb["total_value"] == pytest.approx(100.0)
        # STEAM had only pre-epoch bets -> not present post-epoch.
        assert "STEAM" not in led
        assert led["STEAM_LL"]["open_stake"] == pytest.approx(1.0)

    def test_no_epoch_file_counts_everything(self, db, tmp_path):
        from src import strategy_ledger as sl
        led = sl.strategy_ledgers(db, starting=100.0,
                                  epoch_file=str(tmp_path / "missing.json"))
        assert led["TIPSTER_FOREBET"]["settled_pnl"] == pytest.approx(-2.0)
