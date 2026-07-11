"""Tests for the settlement-provenance schema + enforcement trigger.

The trigger guarantees "never assume a result is correct": an OPEN bet can
only become W/L with a mapped scraped source (result_verified=1 + settle_source).
"""
import sqlite3

import pytest

from src.settlement_provenance import (
    PROVENANCE_COLUMNS,
    TRIGGER_NAME,
    ensure_settlement_provenance,
    has_trigger,
)

_MINIMAL_BET_LOG = """
CREATE TABLE bet_log (
    bet_id TEXT PRIMARY KEY,
    match_id TEXT,
    result TEXT DEFAULT 'OPEN',
    pnl REAL DEFAULT 0
)
"""


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "bet_log.db"
    conn = sqlite3.connect(p)
    conn.execute(_MINIMAL_BET_LOG)
    conn.execute(
        "INSERT INTO bet_log (bet_id, match_id, result) VALUES ('b1', 'A vs B', 'OPEN')"
    )
    conn.commit()
    conn.close()
    ensure_settlement_provenance(str(p))
    return str(p)


def test_columns_added(db):
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bet_log)")}
    conn.close()
    for c in PROVENANCE_COLUMNS:
        assert c in cols


def test_trigger_installed(db):
    assert has_trigger(db) is True


def test_migration_is_idempotent(db):
    # second run must not raise or duplicate anything
    ensure_settlement_provenance(db)
    ensure_settlement_provenance(db)
    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name=?",
        (TRIGGER_NAME,),
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_unverified_win_is_blocked(db):
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE bet_log SET result='W', pnl=10 WHERE bet_id='b1'")
    conn.close()
    # row unchanged
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT result FROM bet_log WHERE bet_id='b1'").fetchone()[0] == "OPEN"
    conn.close()


def test_win_with_source_but_not_verified_is_blocked(db):
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE bet_log SET result='L', settle_source='name-match', "
            "result_verified=0 WHERE bet_id='b1'"
        )
    conn.close()


def test_verified_win_is_allowed(db):
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE bet_log SET result='W', pnl=10, settle_source='name-match', "
        "result_verified=1, settle_reason='A vs B' WHERE bet_id='b1'"
    )
    conn.commit()
    assert conn.execute("SELECT result FROM bet_log WHERE bet_id='b1'").fetchone()[0] == "W"
    conn.close()


def test_void_is_always_allowed_without_source(db):
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE bet_log SET result='VOID', pnl=0, "
        "settle_reason='no result 48h past kickoff' WHERE bet_id='b1'"
    )
    conn.commit()
    assert conn.execute("SELECT result FROM bet_log WHERE bet_id='b1'").fetchone()[0] == "VOID"
    conn.close()


def test_regrade_on_already_settled_row_not_blocked(db):
    # settle it verified first
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE bet_log SET result='W', settle_source='name-match', "
        "result_verified=1 WHERE bet_id='b1'"
    )
    conn.commit()
    # a later unrelated UPDATE that re-touches result but keeps it W and drops
    # the verified flag must NOT be blocked (guard is OPEN->W/L only)
    conn.execute("UPDATE bet_log SET result='W', result_verified=0 WHERE bet_id='b1'")
    conn.commit()
    conn.close()


def test_noop_when_bet_log_absent(tmp_path):
    p = tmp_path / "empty.db"
    sqlite3.connect(p).close()
    assert ensure_settlement_provenance(str(p)) is False
