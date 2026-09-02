"""One-time reclamation of the unbounded sharp_odds_history table.

The live fix (dedup + per-cycle purge in pinnacle_feed) bounds FUTURE growth.
This tool reclaims what already accumulated: 65M rows / 16.6 GB built up over
63 days because nothing ever deleted from this table.

Deleting 51M rows row-by-row would thrash three indexes, so the tool rebuilds
the table from the rows worth keeping and swaps it in, then VACUUMs. These
tests pin the data contract: retention boundary, index restoration, and that
the schema the readers depend on survives the swap.
"""

import importlib
import sqlite3
import time

import pytest

prune_mod = importlib.import_module("tools.prune_sharp_odds_history")

_INSERT = (
    "INSERT INTO sharp_odds_history "
    "(match_key, home_team, away_team, league, selection, decimal_odds, devig_prob, ts, starts_ts) "
    "VALUES (?,?,?,?,?,?,?,?,?)"
)


@pytest.fixture
def db(tmp_path):
    """A miniature sharp_odds_history with old and recent rows."""
    path = str(tmp_path / "completed_fixtures.db")
    con = sqlite3.connect(path)
    con.execute(
        """CREATE TABLE sharp_odds_history (
            match_key TEXT, home_team TEXT, away_team TEXT, league TEXT,
            selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL
        )"""
    )
    con.execute("CREATE INDEX idx_soh_ts ON sharp_odds_history(ts)")
    con.execute(
        "CREATE INDEX idx_soh_teams ON sharp_odds_history(home_team, away_team, selection)"
    )
    con.execute(
        "CREATE INDEX idx_soh_norm ON sharp_odds_history("
        "LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' ')),"
        "LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' ')),"
        "selection)"
    )
    # An unrelated table must survive untouched.
    con.execute("CREATE TABLE steam_signals (fixture_id TEXT, note TEXT)")
    con.execute("INSERT INTO steam_signals VALUES ('1','keep me')")

    now = time.time()
    rows = []
    for d in (60, 40, 20, 13, 5, 0):  # days ago
        for sel in ("home", "draw", "away"):
            rows.append(
                (
                    f"T{d} vs U{d}",
                    f"T{d}",
                    f"U{d}",
                    "L",
                    sel,
                    2.0,
                    0.5,
                    now - d * 86400,
                    now,
                )
            )
    con.executemany(_INSERT, rows)
    con.commit()
    con.close()
    return path


def _count(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM sharp_odds_history").fetchone()[0]
    finally:
        con.close()


def _indexes(path):
    con = sqlite3.connect(path)
    try:
        return {
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='sharp_odds_history' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        con.close()


# ---------------------------------------------------------------------------


def test_keeps_rows_inside_retention_and_drops_older(db):
    assert _count(db) == 18  # 6 days x 3 selections

    prune_mod.prune(db, days=14, vacuum=False)

    con = sqlite3.connect(db)
    keys = {r[0] for r in con.execute("SELECT DISTINCT match_key FROM sharp_odds_history")}
    con.close()
    assert keys == {"T13 vs U13", "T5 vs U5", "T0 vs U0"}
    assert _count(db) == 9


def test_indexes_are_restored_after_the_swap(db):
    before = _indexes(db)
    assert before == {"idx_soh_ts", "idx_soh_teams", "idx_soh_norm"}

    prune_mod.prune(db, days=14, vacuum=False)

    assert _indexes(db) == before, "readers depend on idx_soh_norm for their lookups"


def test_expression_index_is_actually_used_after_prune(db):
    """idx_soh_norm is what keeps _pinnacle_fallback_odds() off a full scan."""
    prune_mod.prune(db, days=14, vacuum=False)
    con = sqlite3.connect(db)
    plan = con.execute(
        "EXPLAIN QUERY PLAN SELECT decimal_odds FROM sharp_odds_history "
        "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
        "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=? "
        "AND selection=? ORDER BY ts DESC LIMIT 1",
        ("t0", "u0", "home"),
    ).fetchall()
    con.close()
    assert any("idx_soh_norm" in str(r) for r in plan), plan


def test_schema_columns_are_preserved(db):
    prune_mod.prune(db, days=14, vacuum=False)
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(sharp_odds_history)")]
    con.close()
    assert cols == [
        "match_key",
        "home_team",
        "away_team",
        "league",
        "selection",
        "decimal_odds",
        "devig_prob",
        "ts",
        "starts_ts",
    ]


def test_other_tables_are_untouched(db):
    prune_mod.prune(db, days=14, vacuum=False)
    con = sqlite3.connect(db)
    got = con.execute("SELECT note FROM steam_signals").fetchall()
    con.close()
    assert got == [("keep me",)]


def test_dry_run_changes_nothing(db):
    stats = prune_mod.prune(db, days=14, dry_run=True)
    assert _count(db) == 18
    assert stats["rows_before"] == 18
    assert stats["rows_to_keep"] == 9


def test_reports_before_and_after_counts(db):
    stats = prune_mod.prune(db, days=14, vacuum=False)
    assert stats["rows_before"] == 18
    assert stats["rows_after"] == 9
    assert stats["rows_removed"] == 9


def test_missing_db_is_a_no_op(tmp_path):
    stats = prune_mod.prune(str(tmp_path / "nope.db"), days=14)
    assert stats["rows_before"] == 0
    assert stats["rows_removed"] == 0


def test_retention_default_matches_the_live_feed(db):
    """The tool and the running daemon must agree on the window."""
    import src.pinnacle_feed as pf

    assert prune_mod.DEFAULT_RETENTION_DAYS == pf.SHARP_ODDS_RETENTION_DAYS


# ---------------------------------------------------------------------------
# archive — the prune must be reversible, not a data loss
# ---------------------------------------------------------------------------


def test_archive_captures_exactly_the_dropped_rows(db, tmp_path):
    arch = str(tmp_path / "archive.db")

    con = sqlite3.connect(db)
    now = time.time()
    expected = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT match_key FROM sharp_odds_history WHERE ts < ?",
            (now - 14 * 86400,),
        )
    }
    con.close()

    stats = prune_mod.prune(db, days=14, vacuum=False, archive_path=arch)

    assert stats["rows_archived"] == stats["rows_removed"] == 9
    acon = sqlite3.connect(arch)
    got = {r[0] for r in acon.execute("SELECT DISTINCT match_key FROM sharp_odds_history")}
    n = acon.execute("SELECT COUNT(*) FROM sharp_odds_history").fetchone()[0]
    acon.close()
    assert got == expected == {"T60 vs U60", "T40 vs U40", "T20 vs U20"}
    assert n == 9


def test_archive_plus_live_reconstructs_the_original(db, tmp_path):
    """No row is lost: archive + pruned table == what we started with."""
    arch = str(tmp_path / "archive.db")
    before = _count(db)

    prune_mod.prune(db, days=14, vacuum=False, archive_path=arch)

    acon = sqlite3.connect(arch)
    archived = acon.execute("SELECT COUNT(*) FROM sharp_odds_history").fetchone()[0]
    acon.close()
    assert _count(db) + archived == before


def test_no_archive_path_means_no_sidecar_file(db, tmp_path):
    stats = prune_mod.prune(db, days=14, vacuum=False)
    assert stats["rows_archived"] == 0
    assert not (tmp_path / "sharp_odds_history_archive.db").exists()
