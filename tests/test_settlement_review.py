"""Tests for the manual-review queue (src/settlement_review.py).

When settlement cannot map a finished bet to any covered results source, it must
NOT grade it from a fuzzy collision (the Uruguay-Tercera-Reserves / Australian-NPL
coverage-gap class). Instead the bet is left OPEN and recorded here so an operator
can settle it from a verified source — or void it — rather than the system either
silently leaving it OPEN forever or auto-voiding a genuinely-settleable result.
"""
import sqlite3

import pytest

from src.settlement_review import (
    REVIEW_TABLE,
    ensure_review_queue,
    has_review_table,
    list_review_queue,
    queue_for_review,
    resolve_review,
)


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "bet_log.db"
    sqlite3.connect(p).close()
    ensure_review_queue(str(p))
    return str(p)


def test_ensure_creates_table(db):
    assert has_review_table(db) is True


def test_ensure_is_idempotent(tmp_path):
    p = str(tmp_path / "bet_log.db")
    sqlite3.connect(p).close()
    assert ensure_review_queue(p) is True
    assert ensure_review_queue(p) is True
    assert has_review_table(p) is True


def test_has_review_table_false_before_ensure(tmp_path):
    p = str(tmp_path / "empty.db")
    sqlite3.connect(p).close()
    assert has_review_table(p) is False


def test_queue_inserts_a_pending_row(db):
    queue_for_review(
        db,
        bet_id="b1",
        match_id="River Plate Reserves vs Racing Club Reserves",
        market_type="1X2",
        league="Reserves Leagues U23",
        reason="no covered results source has this fixture",
    )
    rows = list_review_queue(db)
    assert len(rows) == 1
    r = rows[0]
    assert r["bet_id"] == "b1"
    assert r["match_id"] == "River Plate Reserves vs Racing Club Reserves"
    assert r["market_type"] == "1X2"
    assert r["league"] == "Reserves Leagues U23"
    assert r["reason"] == "no covered results source has this fixture"
    assert r["resolved"] == 0
    assert r["queued_at"]


def test_queue_is_idempotent_one_row_per_bet(db):
    queue_for_review(db, "b1", match_id="A vs B", reason="first")
    queue_for_review(db, "b1", match_id="A vs B", reason="second refreshed")
    rows = list_review_queue(db)
    assert len(rows) == 1
    assert rows[0]["reason"] == "second refreshed"


def test_queue_self_ensures_table(tmp_path):
    # queue_for_review must work even if ensure_review_queue was never called.
    p = str(tmp_path / "bet_log.db")
    sqlite3.connect(p).close()
    queue_for_review(p, "b1", match_id="A vs B", reason="r")
    assert has_review_table(p) is True
    assert len(list_review_queue(p)) == 1


def test_resolve_marks_row_resolved(db):
    queue_for_review(db, "b1", match_id="A vs B", reason="r")
    resolve_review(db, "b1", resolution="operator settled W from Sofascore")
    rows = list_review_queue(db, include_resolved=True)
    assert len(rows) == 1
    assert rows[0]["resolved"] == 1
    assert rows[0]["resolution"] == "operator settled W from Sofascore"
    assert rows[0]["resolved_at"]


def test_list_excludes_resolved_by_default(db):
    queue_for_review(db, "b1", match_id="A vs B", reason="r")
    queue_for_review(db, "b2", match_id="C vs D", reason="r")
    resolve_review(db, "b1")
    pending = list_review_queue(db)
    assert {r["bet_id"] for r in pending} == {"b2"}


def test_requeue_does_not_reopen_a_resolved_row(db):
    queue_for_review(db, "b1", match_id="A vs B", reason="r")
    resolve_review(db, "b1", resolution="done")
    # A later settlement sweep re-encounters the same still-unmapped bet.
    queue_for_review(db, "b1", match_id="A vs B", reason="seen again")
    rows = list_review_queue(db, include_resolved=True)
    assert len(rows) == 1
    assert rows[0]["resolved"] == 1  # operator's resolution preserved
    assert rows[0]["resolution"] == "done"


def test_resolve_missing_bet_is_noop(db):
    resolve_review(db, "does-not-exist")  # must not raise
    assert list_review_queue(db, include_resolved=True) == []


def test_review_table_name_constant():
    assert REVIEW_TABLE == "settlement_review"
