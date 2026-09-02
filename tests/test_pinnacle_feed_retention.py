"""sharp_odds_history growth-control tests.

The Pinnacle feed appended every polled price unconditionally every
POLL_INTERVAL seconds, with no retention. That grew the table to 65M rows /
16.6 GB (~1.03M rows/day), which is the dominant disk+page-cache cost in the
system. These tests pin the two controls that bound it:

  1. write_snapshot()/write_ou25_snapshot() skip a price that has NOT changed
     and was last written within HEARTBEAT_SEC (dedup), but still write a
     periodic heartbeat row so "latest row" stays fresh for the daemon's
     60-minute staleness gate and so COUNT(*) reliability gates still climb.
  2. purge_sharp_odds_history() drops rows older than the retention window.

No network — write_snapshot() is fed hand-built snapshot dicts.
"""

import importlib
import sqlite3
import time

import pytest


@pytest.fixture
def feed(tmp_path, monkeypatch):
    """pinnacle_feed module pointed at a tmp completed_fixtures.db."""
    pf = importlib.import_module("src.pinnacle_feed")
    sub = tmp_path / "deepfield_browser_data"
    sub.mkdir(parents=True)
    db = sub / "completed_fixtures.db"
    monkeypatch.setattr(pf, "_COMPLETED_DB", str(db))
    pf._db_path = str(db)  # convenience handle for the tests
    return pf


def _snap(h="Arsenal", a="Chelsea", hd=2.00, dd=3.40, ad=4.10, starts=None):
    return [
        {
            "match_key": f"{h} vs {a}",
            "home_team": h,
            "away_team": a,
            "league": "EPL",
            "h_dec": hd,
            "d_dec": dd,
            "a_dec": ad,
            "p_home": 0.45,
            "p_draw": 0.28,
            "p_away": 0.27,
            "starts_ts": starts if starts is not None else time.time() + 7200,
        }
    ]


def _rows(pf):
    con = sqlite3.connect(pf._db_path)
    try:
        return con.execute(
            "SELECT match_key, selection, decimal_odds, ts "
            "FROM sharp_odds_history ORDER BY ts, selection"
        ).fetchall()
    finally:
        con.close()


def _count(pf):
    con = sqlite3.connect(pf._db_path)
    try:
        return con.execute("SELECT COUNT(*) FROM sharp_odds_history").fetchone()[0]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------


def test_first_snapshot_writes_all_three_selections(feed):
    feed.write_snapshot(_snap())
    assert _count(feed) == 3


def test_unchanged_price_within_heartbeat_is_not_rewritten(feed):
    """The core fix: re-polling an unmoved line must not append duplicate rows."""
    feed.write_snapshot(_snap())
    assert _count(feed) == 3

    # Same prices again, immediately (as the 45s poll loop would do).
    for _ in range(5):
        feed.write_snapshot(_snap())

    assert _count(feed) == 3, "unchanged prices must be deduped, not appended"


def test_changed_price_is_always_written(feed):
    """Real line movement is the signal — it must never be deduped away."""
    feed.write_snapshot(_snap(hd=2.00))
    feed.write_snapshot(_snap(hd=1.91))  # home moved

    rows = [r for r in _rows(feed) if r[1] == "home"]
    assert [r[2] for r in rows] == [2.00, 1.91]

    # draw/away did not move -> still one row each
    assert len([r for r in _rows(feed) if r[1] == "draw"]) == 1
    assert len([r for r in _rows(feed) if r[1] == "away"]) == 1


def test_heartbeat_row_written_once_interval_elapses(feed, monkeypatch):
    """Latest-row ts must stay fresh for the daemon's 60-min staleness gate,
    and COUNT(*) reliability gates must keep climbing, even on a static line."""
    feed.write_snapshot(_snap())
    assert _count(feed) == 3

    # Jump past the heartbeat window with prices unchanged.
    real_time = time.time
    monkeypatch.setattr(
        feed.time, "time", lambda: real_time() + feed.HEARTBEAT_SEC + 1
    )
    feed.write_snapshot(_snap())

    assert _count(feed) == 6, "a heartbeat row must be written once HEARTBEAT_SEC passes"


def test_heartbeat_is_well_inside_the_staleness_gate(feed):
    """The daemon rejects Pinnacle odds older than max_odds_staleness_min (60).
    The heartbeat must refresh far more often than that."""
    assert feed.HEARTBEAT_SEC <= 30 * 60


def test_dedup_is_per_selection_and_per_match(feed):
    feed.write_snapshot(_snap(h="Arsenal", a="Chelsea", hd=2.00))
    feed.write_snapshot(_snap(h="Spurs", a="Everton", hd=2.00))
    assert _count(feed) == 6

    # Only Arsenal's home price moves.
    feed.write_snapshot(_snap(h="Arsenal", a="Chelsea", hd=1.80))
    feed.write_snapshot(_snap(h="Spurs", a="Everton", hd=2.00))
    assert _count(feed) == 7


def test_ou25_snapshot_dedups_too(feed):
    totals = {
        "Arsenal vs Chelsea": {
            "over": 1.90,
            "under": 1.95,
            "p_over": 0.51,
            "p_under": 0.49,
            "starts_ts": time.time() + 7200,
            "_home": "Arsenal",
            "_away": "Chelsea",
        }
    }
    feed.write_ou25_snapshot(totals)
    assert _count(feed) == 2

    feed.write_ou25_snapshot(totals)
    assert _count(feed) == 2, "unchanged O/U prices must be deduped"

    totals["Arsenal vs Chelsea"]["over"] = 1.85
    feed.write_ou25_snapshot(totals)
    assert _count(feed) == 3


def test_write_snapshot_still_returns_match_count(feed):
    """Callers log this number — dedup must not silently change its meaning."""
    assert feed.write_snapshot(_snap()) == 1


# ---------------------------------------------------------------------------
# retention
# ---------------------------------------------------------------------------


def test_purge_drops_rows_older_than_retention(feed):
    con = sqlite3.connect(feed._db_path)
    feed._ensure_table(con)
    now = time.time()
    old = now - 40 * 86400
    recent = now - 1 * 86400
    con.executemany(
        "INSERT INTO sharp_odds_history "
        "(match_key, home_team, away_team, league, selection, decimal_odds, devig_prob, ts, starts_ts) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("Old vs Match", "Old", "Match", "", "home", 2.0, 0.5, old, old),
            ("New vs Match", "New", "Match", "", "home", 2.0, 0.5, recent, recent),
        ],
    )
    con.commit()
    con.close()

    removed = feed.purge_sharp_odds_history(days=14)

    assert removed == 1
    rows = _rows(feed)
    assert len(rows) == 1
    assert rows[0][0] == "New vs Match"


def test_purge_is_safe_on_missing_db(tmp_path, monkeypatch):
    pf = importlib.import_module("src.pinnacle_feed")
    monkeypatch.setattr(pf, "_COMPLETED_DB", str(tmp_path / "nope" / "missing.db"))
    assert pf.purge_sharp_odds_history(days=14) == 0


def test_purge_retention_default_covers_settlement_lookback(feed):
    """settle_open_bets() looks back up to 7 days; wc_upcoming injects 7 days
    ahead. Retention must comfortably span both."""
    assert feed.SHARP_ODDS_RETENTION_DAYS >= 14


def test_heartbeat_still_reaches_the_reliability_gate_quickly(feed):
    """check_value() and _pinnacle_fallback_odds() both require COUNT(*) >= 10
    snapshots before trusting a Pinnacle price. On a line that never moves, the
    heartbeat alone must clear that bar well inside a typical listing window."""
    minutes_to_ten = (10 * feed.HEARTBEAT_SEC) / 60.0
    assert minutes_to_ten <= 60, (
        f"a static line would need {minutes_to_ten:.0f} min to reach 10 snapshots"
    )
