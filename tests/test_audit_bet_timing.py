"""Tests for tools/audit_bet_timing.py — durable placement-vs-kickoff audit.

Answers the question a retroactive investigation (2026-07-13) found impossible
to answer reliably from odds_stream.db alone (it only retains ~3 days):
was this bet placed before the match started, or after (in-play, on stale
pre-match odds)? Requires kickoff_time to have been captured at placement
time (see tools/migrate_bet_log.py + place_tipster_bets/log_ai_bet/
log_steam_bet), so legacy bets placed before that column existed are
correctly reported as unauditable rather than silently skipped or assumed OK.
"""

import sqlite3

import pytest

from tools.audit_bet_timing import audit_timing

SCHEMA = """
    CREATE TABLE bet_log (
        bet_id TEXT PRIMARY KEY, match_id TEXT, bet_source TEXT,
        placed_at TEXT, kickoff_time TEXT, result TEXT
    )
"""


def _mk_db(tmp_path, rows):
    db = str(tmp_path / "bet_log.db")
    conn = sqlite3.connect(db)
    conn.execute(SCHEMA)
    conn.executemany(
        "INSERT INTO bet_log (bet_id, match_id, bet_source, placed_at, kickoff_time, result) "
        "VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


class TestAuditTiming:
    def test_pre_kickoff_placement_is_clean(self, tmp_path):
        db = _mk_db(tmp_path, [
            ("b1", "A vs B", "TIPSTER_FOREBET", "2026-07-10T08:00:00Z", "2026-07-10T15:00:00Z", "W"),
        ])
        result = audit_timing(db)
        assert result["checked"] == 1
        assert result["violations"] == []

    def test_post_kickoff_placement_is_flagged(self, tmp_path):
        db = _mk_db(tmp_path, [
            ("b2", "C vs D", "TIPSTER_FOREBET", "2026-07-10T15:20:00Z", "2026-07-10T15:00:00Z", "W"),
        ])
        result = audit_timing(db)
        assert result["checked"] == 1
        assert len(result["violations"]) == 1
        v = result["violations"][0]
        assert v["bet_id"] == "b2"
        assert v["minutes_late"] == pytest.approx(20.0)

    def test_exact_kickoff_moment_counts_as_violation(self, tmp_path):
        """delta == 0 is in-play, not pre-match — must not slip through as clean."""
        db = _mk_db(tmp_path, [
            ("b3", "E vs F", "AI", "2026-07-10T15:00:00Z", "2026-07-10T15:00:00Z", "L"),
        ])
        result = audit_timing(db)
        assert len(result["violations"]) == 1

    def test_missing_kickoff_time_reported_separately_not_silently_ok(self, tmp_path):
        """Legacy bets with no kickoff_time recorded must show up as
        unauditable, never counted as 'checked' or implicitly clean."""
        db = _mk_db(tmp_path, [
            ("b4", "G vs H", "TIPSTER_FOREBET", "2026-07-10T08:00:00Z", None, "W"),
        ])
        result = audit_timing(db)
        assert result["checked"] == 0
        assert result["missing_kickoff"] == 1
        assert result["violations"] == []

    def test_unparseable_timestamp_reported_as_unparseable_not_dropped(self, tmp_path):
        db = _mk_db(tmp_path, [
            ("b5", "I vs J", "AI", "not-a-timestamp", "2026-07-10T15:00:00Z", "W"),
        ])
        result = audit_timing(db)
        assert result["checked"] == 0
        assert result["unparseable"] == 1

    def test_midnight_placeholder_same_day_is_not_a_violation(self, tmp_path):
        """Kickertech/Betarabia record 00:00:00 as a DATE-ONLY placeholder when
        the real kickoff time is unknown (same convention _fixture_has_started()
        already special-cases). A bet placed later the same day must NOT be
        flagged as 'placed after kickoff' -- the true kickoff time is simply
        unrecorded, not proven to be in the past. Regression: the first version
        of this tool flagged 5 real bets this way (2026-07-13)."""
        db = _mk_db(tmp_path, [
            ("mid", "K vs L", "TIPSTER_APIFB", "2026-07-13T08:49:17Z", "2026-07-13T00:00:00.000Z", "OPEN"),
        ])
        result = audit_timing(db)
        assert result["violations"] == []
        assert result["unknown_time_placeholder"] == 1
        assert result["checked"] == 0

    def test_midnight_placeholder_past_date_is_still_a_violation(self, tmp_path):
        """A placeholder whose DATE is already in the past is a genuine
        violation -- the match clearly finished before placement."""
        db = _mk_db(tmp_path, [
            ("mid2", "M vs N", "TIPSTER_APIFB", "2026-07-13T08:49:17Z", "2026-07-10T00:00:00.000Z", "OPEN"),
        ])
        result = audit_timing(db)
        assert len(result["violations"]) == 1
        assert result["violations"][0]["bet_id"] == "mid2"

    def test_mixed_batch_all_categories(self, tmp_path):
        db = _mk_db(tmp_path, [
            ("clean", "A vs B", "AI", "2026-07-10T08:00:00Z", "2026-07-10T15:00:00Z", "W"),
            ("late", "C vs D", "AI", "2026-07-10T15:20:00Z", "2026-07-10T15:00:00Z", "L"),
            ("missing", "E vs F", "AI", "2026-07-10T08:00:00Z", None, "W"),
        ])
        result = audit_timing(db)
        assert result["checked"] == 2
        assert result["missing_kickoff"] == 1
        assert len(result["violations"]) == 1
        assert result["violations"][0]["bet_id"] == "late"
