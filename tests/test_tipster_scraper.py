"""
Unit tests for src/tipster_scraper.py's _build_odds_map() — the bookmaker
collision fix (2026-07-09).

Bug: odds_stream.db's `market` table stores odds from MULTIPLE bookmakers
under the same (fixture_id, market_name, selection_name) key. The previous
implementation built the odds lookup with a plain per-row dict assignment,
so whichever row SQLite returned last silently won -- an arbitrary
bookmaker's price, not a representative one. Real example that surfaced
this: France vs Morocco's "France" selection had 19 bookmaker rows from
1.00 to 12.00; the code picked up 10.0 (an outlier) instead of the 1.63
most bookmakers agreed on.
"""

import datetime

import pytest

from src.tipster_scraper import (
    _build_odds_map,
    _fixture_has_started,
    _kambi_odds_for_side,
    _make_kambi_fixture_id,
)

_UTC = datetime.timezone.utc
_NOW = datetime.datetime(2026, 7, 11, 5, 30, 45, tzinfo=_UTC)


def test_single_bookmaker_row_unchanged():
    rows = [("F1", "Match Result", "France", 1.63)]
    odds_map = _build_odds_map(rows)
    assert odds_map[("F1", "Match Result", "France")] == 1.63


def test_multiple_bookmakers_use_median_not_last_write():
    # Mirrors the real France vs Morocco data: most bookmakers cluster near
    # 1.63, with a couple of outliers (10.0, 12.0) that a last-write-wins
    # dict would have picked up if they happened to be scraped last.
    rows = [
        ("F1", "Match Result", "France", 1.63),
        ("F1", "Match Result", "France", 1.2),
        ("F1", "Match Result", "France", 1.7),
        ("F1", "Match Result", "France", 1.63),
        ("F1", "Match Result", "France", 10.0),  # outlier, scraped last
    ]
    odds_map = _build_odds_map(rows)
    # median of [1.2, 1.63, 1.63, 1.7, 10.0] = 1.63
    assert odds_map[("F1", "Match Result", "France")] == 1.63


def test_even_count_uses_average_of_middle_two():
    rows = [
        ("F1", "Match Result", "Home", 1.5),
        ("F1", "Match Result", "Home", 1.7),
        ("F1", "Match Result", "Home", 1.9),
        ("F1", "Match Result", "Home", 2.1),
    ]
    odds_map = _build_odds_map(rows)
    # median of [1.5, 1.7, 1.9, 2.1] = (1.7+1.9)/2 = 1.8
    assert odds_map[("F1", "Match Result", "Home")] == pytest.approx(1.8)


def test_zero_or_falsy_odds_excluded():
    rows = [
        ("F1", "Match Result", "France", 1.63),
        ("F1", "Match Result", "France", 0),  # excluded -- not a real price
        ("F1", "Match Result", "France", None),  # excluded
    ]
    odds_map = _build_odds_map(rows)
    assert odds_map[("F1", "Match Result", "France")] == 1.63


def test_different_keys_kept_independent():
    rows = [
        ("F1", "Match Result", "France", 1.63),
        ("F1", "Match Result", "Morocco", 6.25),
        ("F1", "Match Result", "X", 3.85),
        ("F2", "Match Result", "France", 2.0),  # different fixture, same selection name
    ]
    odds_map = _build_odds_map(rows)
    assert odds_map[("F1", "Match Result", "France")] == 1.63
    assert odds_map[("F1", "Match Result", "Morocco")] == 6.25
    assert odds_map[("F1", "Match Result", "X")] == 3.85
    assert odds_map[("F2", "Match Result", "France")] == 2.0


def test_empty_rows_returns_empty_map():
    assert _build_odds_map([]) == {}


# ---------------------------------------------------------------------------
# Kambi fallback (2026-07-10) — covers fixtures Betarabia doesn't have
# ---------------------------------------------------------------------------
KAMBI_MATCH = {
    "home": 1.85, "draw": 3.4, "away": 4.2,
    "home_team": "Oakleigh Cannons", "away_team": "Avondale FC",
    "league": "NPL Victoria",
}


def test_kambi_odds_for_side_maps_home_draw_away():
    assert _kambi_odds_for_side(KAMBI_MATCH, "Home (1)") == 1.85
    assert _kambi_odds_for_side(KAMBI_MATCH, "Draw (X)") == 3.4
    assert _kambi_odds_for_side(KAMBI_MATCH, "Away (2)") == 4.2


def test_kambi_odds_for_side_unknown_side_returns_none():
    assert _kambi_odds_for_side(KAMBI_MATCH, "not a side") is None


def test_kambi_odds_for_side_missing_price_returns_none():
    assert _kambi_odds_for_side({"home": 1.85}, "Draw (X)") is None
    assert _kambi_odds_for_side({"home": 1.85, "draw": 0}, "Draw (X)") is None


def test_make_kambi_fixture_id_stable_and_prefixed():
    fid1 = _make_kambi_fixture_id("Oakleigh Cannons", "Avondale FC")
    fid2 = _make_kambi_fixture_id("Oakleigh Cannons", "Avondale FC")
    assert fid1 == fid2  # deterministic
    assert fid1.startswith("KAMBI_")


def test_make_kambi_fixture_id_distinct_per_matchup():
    fid1 = _make_kambi_fixture_id("Oakleigh Cannons", "Avondale FC")
    fid2 = _make_kambi_fixture_id("Avondale FC", "Oakleigh Cannons")  # swapped
    fid3 = _make_kambi_fixture_id("Preston Lions", "Hume City")
    assert len({fid1, fid2, fid3}) == 3


# ---------------------------------------------------------------------------
# In-play placement guard (2026-07-12): never place a pre-match bet on a fixture
# whose real kickoff has already passed (stale-odds in-play bet). The 2026-07-11
# Australian-NPL bets placed 7-27 min AFTER kickoff are the motivating bug.
# ---------------------------------------------------------------------------

class TestFixtureHasStarted:
    def test_real_past_kickoff_is_started(self):
        fix = {"kickoff_time": "2026-07-11T05:15:00.000Z"}  # 15 min before now
        assert _fixture_has_started(fix, _NOW) is True

    def test_upcoming_kickoff_is_not_started(self):
        fix = {"kickoff_time": "2026-07-11T20:00:00.000Z"}  # hours away
        assert _fixture_has_started(fix, _NOW) is False

    def test_exact_kickoff_now_counts_as_started(self):
        fix = {"kickoff_time": _NOW.isoformat()}
        assert _fixture_has_started(fix, _NOW) is True

    def test_missing_kickoff_fails_open(self):
        # No kickoff data -> never block a placement on absent data.
        assert _fixture_has_started({}, _NOW) is False
        assert _fixture_has_started({"kickoff_time": None}, _NOW) is False

    def test_unparseable_kickoff_fails_open(self):
        assert _fixture_has_started({"kickoff_time": "not-a-date"}, _NOW) is False

    def test_naive_timestamp_treated_as_utc(self):
        fix = {"kickoff_time": "2026-07-11T05:00:00"}  # no tz -> UTC, 30 min ago
        assert _fixture_has_started(fix, _NOW) is True

    def test_midnight_placeholder_same_day_fails_open(self):
        # Kickertech uses 00:00:00 as a date-only placeholder when the real time
        # is unknown. A same-day placeholder must NOT block a bet — the match may
        # still be hours away; over-blocking would silently halt legit betting.
        fix = {"kickoff_time": "2026-07-11T00:00:00.000Z"}
        assert _fixture_has_started(fix, _NOW) is False

    def test_midnight_placeholder_past_date_is_started(self):
        # A placeholder whose DATE is already in the past definitely finished.
        fix = {"kickoff_time": "2026-07-10T00:00:00.000Z"}
        assert _fixture_has_started(fix, _NOW) is True

    def test_kickoff_date_fallback_past_date_is_started(self):
        fix = {"kickoff_date": "2026-07-09"}  # only a date, in the past
        assert _fixture_has_started(fix, _NOW) is True

    def test_default_now_is_utc_now(self):
        # A clearly-past kickoff is started even without an explicit `now`.
        fix = {"kickoff_time": "2020-01-01T00:00:00.000Z"}
        assert _fixture_has_started(fix) is True


class TestPlacementSkipsInPlay:
    """place_tipster_bets() must skip fixtures already kicked off, so no in-play
    bet on stale pre-match odds is ever written (the 2026-07-11 bug)."""

    _BET_LOG_SCHEMA = """
        CREATE TABLE bet_log (
            bet_id TEXT PRIMARY KEY, match_id TEXT, player_id TEXT, market_type TEXT,
            line TEXT, side TEXT, entry_odds REAL, fair_odds REAL, edge_pct REAL,
            stake REAL, book TEXT, placed_at TEXT, lineup_drop_at TEXT, latency_ms INTEGER,
            closing_odds REAL, clv REAL, result TEXT DEFAULT 'OPEN', pnl REAL DEFAULT 0,
            regime TEXT, role_shift_flag INTEGER, bet_source TEXT, is_recommended INTEGER,
            model_version TEXT, fixture_id TEXT, league TEXT, clv_sharp REAL, best_odds REAL,
            best_book TEXT, signal_name TEXT, move_size REAL, monotonicity REAL, pinnacle_clv REAL
        )
    """

    def _setup(self, tmp_path):
        import sqlite3

        odds_db = str(tmp_path / "odds_stream.db")
        bet_db = str(tmp_path / "bet_log.db")
        far_future = "2026-12-31T23:00:00.000Z"
        long_past = "2026-07-11T05:15:00.000Z"  # a real time, before "now"
        oc = sqlite3.connect(odds_db)
        oc.execute(
            "CREATE TABLE fixture (fixture_id TEXT, home_team TEXT, away_team TEXT, "
            "tournament_name TEXT, kickoff_time TEXT, kickoff_date TEXT)"
        )
        oc.execute(
            "CREATE TABLE market (fixture_id TEXT, market_name TEXT, selection_name TEXT, raw_odds REAL)"
        )
        oc.executemany(
            "INSERT INTO fixture VALUES (?,?,?,?,?,?)",
            [
                ("F_UP", "Alpha City", "Beta United", "NPL", far_future, "2026-12-31"),
                ("F_STARTED", "Gamma Town", "Delta FC", "NPL", long_past, "2026-07-11"),
            ],
        )
        oc.executemany(
            "INSERT INTO market VALUES (?,?,?,?)",
            [
                ("F_UP", "Match Result", "Home", 1.8),
                ("F_STARTED", "Match Result", "Home", 1.8),
            ],
        )
        oc.commit()
        oc.close()
        sqlite3.connect(bet_db).executescript(self._BET_LOG_SCHEMA)
        return odds_db, bet_db

    def _predictions(self):
        return [
            {"home_team": "Alpha City", "away_team": "Beta United",
             "source": "TESTSRC", "predicted_side": "Home (1)", "confidence": 55.0},
            {"home_team": "Gamma Town", "away_team": "Delta FC",
             "source": "TESTSRC", "predicted_side": "Home (1)", "confidence": 55.0},
        ]

    def test_started_fixture_is_skipped_upcoming_is_placed(self, tmp_path, monkeypatch):
        import sqlite3
        import datetime as _dt

        import src.tipster_scraper as ts

        odds_db, bet_db = self._setup(tmp_path)
        monkeypatch.setattr(ts, "_paper_balance", lambda: 1000.0)
        # Freeze "now" between the two kickoffs so F_STARTED is in-play, F_UP is future.
        monkeypatch.setattr(
            ts, "_placement_now", lambda: _dt.datetime(2026, 7, 11, 5, 30, 45, tzinfo=_UTC)
        )

        placed = ts.place_tipster_bets(self._predictions(), bet_db=bet_db, odds_db=odds_db)

        conn = sqlite3.connect(bet_db)
        fids = {r[0] for r in conn.execute("SELECT fixture_id FROM bet_log")}
        conn.close()
        assert "F_UP" in fids  # upcoming fixture placed
        assert "F_STARTED" not in fids  # in-play fixture skipped
        assert placed == 1
