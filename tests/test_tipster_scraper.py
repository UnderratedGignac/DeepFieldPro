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

import src.tipster_scraper as ts
from src.tipster_scraper import (
    _build_odds_map,
    _fixture_has_started,
    _kambi_odds_for_side,
    _make_kambi_fixture_id,
)

_UTC = datetime.timezone.utc
_NOW = datetime.datetime(2026, 7, 11, 5, 30, 45, tzinfo=_UTC)


@pytest.fixture(autouse=True)
def _no_source_whitelist(monkeypatch, tmp_path):
    """Isolate tests from PRODUCTION state:
    - settings.json source whitelist (tipster_sources_allowed) -> no restriction
      by default; whitelist tests override explicitly.
    - REAL_BANKROLL_DB -> tmp file. FOREBET-source placements route through the
      real-bankroll gate; without this, test bets DEDUCT REAL LEDGER MONEY
      (2026-07-13 incident: ~$17 of phantom test stakes hit real_bankroll.db
      and the polluted exposure then tripped the daily cap inside tests)."""
    monkeypatch.setattr(ts, "_allowed_tipster_sources", lambda: set())
    _rb = str(tmp_path / "real_bankroll_test.db")
    monkeypatch.setattr(ts, "REAL_BANKROLL_DB", _rb)
    from src.bankroll_tracker import init_bankroll_db

    init_bankroll_db(db_path=_rb)  # funded tmp ledger so the FOREBET gate accepts


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
# Bankroll-scaled conviction staking (2026-07-13): the user mirrors picks with
# a real $100 bankroll, so stake sizing must be settings-driven — notional and
# clamps from settings.json instead of the hardcoded $500 / [$2, $25].
# ---------------------------------------------------------------------------

class TestBankrollScaledStaking:
    def test_stake_params_defaults_when_unconfigured(self, monkeypatch, tmp_path):
        # Point BASE_DIR at an empty dir -> no settings.json -> legacy defaults.
        monkeypatch.setattr(ts, "BASE_DIR", str(tmp_path))
        assert ts._stake_params() == (500.0, 2.0, 25.0)

    def test_stake_params_read_from_settings(self, monkeypatch, tmp_path):
        import json, os
        os.makedirs(tmp_path / "data", exist_ok=True)
        (tmp_path / "data" / "settings.json").write_text(
            json.dumps({"stake_notional": 100, "stake_min": 1, "stake_max": 5})
        )
        monkeypatch.setattr(ts, "BASE_DIR", str(tmp_path))
        assert ts._stake_params() == (100.0, 1.0, 5.0)

    def test_kelly_stake_scales_with_notional(self, monkeypatch):
        monkeypatch.setattr(ts, "_stake_params", lambda: (100.0, 1.0, 5.0))
        # p=0.55 @ 2.0: kelly_f = (1.10-1)/1 = 0.10 -> 100 * 0.10 * 0.25 = $2.50
        assert ts._conviction_stake(55.0, 2.0, 1000.0) == pytest.approx(2.5)

    def test_high_conviction_clamps_to_max(self, monkeypatch):
        monkeypatch.setattr(ts, "_stake_params", lambda: (100.0, 1.0, 5.0))
        # p=0.70 @ 3.3 is a huge kelly edge -> clamps to the $5 max (5% of $100)
        assert ts._conviction_stake(70.0, 3.3, 1000.0) == pytest.approx(5.0)

    def test_no_kelly_edge_returns_min(self, monkeypatch):
        monkeypatch.setattr(ts, "_stake_params", lambda: (100.0, 1.0, 5.0))
        # p=0.40 @ 2.0 -> kelly <= 0 -> minimum stake, not the legacy $2
        assert ts._conviction_stake(40.0, 2.0, 1000.0) == pytest.approx(1.0)

    def test_flat_fallback_clamped_to_max(self, monkeypatch):
        monkeypatch.setattr(ts, "_stake_params", lambda: (100.0, 1.0, 5.0))
        # Missing confidence -> flat fallback, but never above the configured max.
        assert ts._conviction_stake(None, 2.0, 1000.0, flat=25.0) == pytest.approx(5.0)


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
            best_book TEXT, signal_name TEXT, move_size REAL, monotonicity REAL, pinnacle_clv REAL,
            kickoff_time TEXT
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

    def test_source_whitelist_blocks_non_forebet_sources(self, tmp_path, monkeypatch):
        """Forebet-only mode (2026-07-13): settings.tipster_sources_allowed
        restricts WHICH tipster sources may place bets. With ['FOREBET'], an
        APIFB prediction for the same fixture must be skipped at the placement
        boundary while the Forebet one places normally."""
        import sqlite3

        import src.tipster_scraper as ts

        odds_db, bet_db = self._setup(tmp_path)
        monkeypatch.setattr(ts, "_paper_balance", lambda: 1000.0)
        monkeypatch.setattr(ts, "_allowed_tipster_sources", lambda: {"FOREBET"})
        preds = [
            {"home_team": "Alpha City", "away_team": "Beta United",
             "source": "FOREBET", "predicted_side": "Home (1)", "confidence": 55.0},
            {"home_team": "Alpha City", "away_team": "Beta United",
             "source": "APIFB", "predicted_side": "Home (1)", "confidence": 55.0},
        ]
        placed = ts.place_tipster_bets(preds, bet_db=bet_db, odds_db=odds_db)

        conn = sqlite3.connect(bet_db)
        sources = {r[0] for r in conn.execute("SELECT bet_source FROM bet_log")}
        conn.close()
        assert sources == {"TIPSTER_FOREBET"}
        assert placed == 1

    def test_source_whitelist_empty_allows_all_sources(self, tmp_path, monkeypatch):
        """No whitelist configured -> every source places (backward compatible)."""
        import sqlite3

        import src.tipster_scraper as ts

        odds_db, bet_db = self._setup(tmp_path)
        monkeypatch.setattr(ts, "_paper_balance", lambda: 1000.0)
        monkeypatch.setattr(ts, "_allowed_tipster_sources", lambda: set())
        preds = [
            {"home_team": "Alpha City", "away_team": "Beta United",
             "source": "FOREBET", "predicted_side": "Home (1)", "confidence": 55.0},
            {"home_team": "Alpha City", "away_team": "Beta United",
             "source": "APIFB", "predicted_side": "Home (1)", "confidence": 55.0},
        ]
        placed = ts.place_tipster_bets(preds, bet_db=bet_db, odds_db=odds_db)
        conn = sqlite3.connect(bet_db)
        sources = {r[0] for r in conn.execute("SELECT bet_source FROM bet_log")}
        conn.close()
        assert sources == {"TIPSTER_FOREBET", "TIPSTER_APIFB"}
        assert placed == 2

    def test_kickoff_time_captured_at_placement(self, tmp_path, monkeypatch):
        """The matched fixture's kickoff_time must be persisted into bet_log
        at placement time, so pre/post-kickoff placement is durably auditable
        later without depending on odds_stream.db's rolling ~3-day retention
        (2026-07-13: a retroactive audit request found this was impossible to
        answer for historical bets because that data had already rolled off)."""
        import sqlite3
        import datetime as _dt

        odds_db, bet_db = self._setup(tmp_path)
        monkeypatch.setattr(ts, "_paper_balance", lambda: 1000.0)
        monkeypatch.setattr(
            ts, "_placement_now", lambda: _dt.datetime(2026, 7, 11, 5, 30, 45, tzinfo=_UTC)
        )

        ts.place_tipster_bets(self._predictions(), bet_db=bet_db, odds_db=odds_db)

        conn = sqlite3.connect(bet_db)
        row = conn.execute(
            "SELECT kickoff_time FROM bet_log WHERE fixture_id = 'F_UP'"
        ).fetchone()
        conn.close()
        assert row[0] == "2026-12-31T23:00:00.000Z"


# ---------------------------------------------------------------------------
# API-Football second signal (2026-07-13): a decorrelated paper-bet source
# for an A/B comparison against Forebet. Free tier = 100 req/day and
# settlement already spends ~3/day, so fetching is cached per fixture per
# day and hard-capped (~40 predictions/day), and only fires for fixtures
# Betarabia/Kambi actually price. CRITICAL: only source=='FOREBET' may touch
# real_bankroll.db (see place_tipster_bets) -- APIFB must stay pure paper.
# ---------------------------------------------------------------------------


class TestApiFootballKey:
    def test_env_var_used_when_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv("API_FOOTBALL_KEY", "env-key-123")
        assert ts._api_football_key(base_dir=str(tmp_path)) == "env-key-123"

    def test_falls_back_to_dotenv_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
        (tmp_path / ".env").write_text("API_FOOTBALL_KEY=dotenv-key-456\n", encoding="utf-8")
        assert ts._api_football_key(base_dir=str(tmp_path)) == "dotenv-key-456"

    def test_env_var_wins_over_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.setenv("API_FOOTBALL_KEY", "env-key")
        (tmp_path / ".env").write_text("API_FOOTBALL_KEY=dotenv-key\n", encoding="utf-8")
        assert ts._api_football_key(base_dir=str(tmp_path)) == "env-key"

    def test_missing_everywhere_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
        assert ts._api_football_key(base_dir=str(tmp_path)) is None


class TestParseApifbPrediction:
    def test_picks_max_percent_as_predicted_side_home(self):
        raw = {"predictions": {"percent": {"home": "55%", "draw": "25%", "away": "20%"}}}
        pred = ts._parse_apifb_prediction(raw, "Team A", "Team B", "2026-07-13")
        assert pred["predicted_side"] == "Home (1)"
        assert pred["confidence"] == 55.0
        assert pred["source"] == "APIFB"
        assert pred["home_team"] == "Team A"
        assert pred["away_team"] == "Team B"
        assert pred["date"] == "2026-07-13"

    def test_picks_draw_when_draw_is_highest(self):
        raw = {"predictions": {"percent": {"home": "30%", "draw": "40%", "away": "30%"}}}
        pred = ts._parse_apifb_prediction(raw, "A", "B", "2026-07-13")
        assert pred["predicted_side"] == "Draw (X)"
        assert pred["confidence"] == 40.0

    def test_picks_away_when_away_is_highest(self):
        raw = {"predictions": {"percent": {"home": "20%", "draw": "20%", "away": "60%"}}}
        pred = ts._parse_apifb_prediction(raw, "A", "B", "2026-07-13")
        assert pred["predicted_side"] == "Away (2)"
        assert pred["confidence"] == 60.0

    def test_under_over_minus_maps_to_under_25(self):
        raw = {
            "predictions": {
                "percent": {"home": "50%", "draw": "30%", "away": "20%"},
                "under_over": "-2.5",
            }
        }
        pred = ts._parse_apifb_prediction(raw, "A", "B", "2026-07-13")
        assert pred["predicted_ou"] == "Under 2.5"

    def test_under_over_plus_maps_to_over_25(self):
        raw = {
            "predictions": {
                "percent": {"home": "50%", "draw": "30%", "away": "20%"},
                "under_over": "+2.5",
            }
        }
        pred = ts._parse_apifb_prediction(raw, "A", "B", "2026-07-13")
        assert pred["predicted_ou"] == "Over 2.5"

    def test_missing_under_over_leaves_predicted_ou_none(self):
        raw = {"predictions": {"percent": {"home": "50%", "draw": "30%", "away": "20%"}}}
        pred = ts._parse_apifb_prediction(raw, "A", "B", "2026-07-13")
        assert pred["predicted_ou"] is None

    def test_missing_percent_returns_none(self):
        raw = {"predictions": {}}
        assert ts._parse_apifb_prediction(raw, "A", "B", "2026-07-13") is None

    def test_none_raw_returns_none(self):
        assert ts._parse_apifb_prediction(None, "A", "B", "2026-07-13") is None

    def test_non_numeric_percent_returns_none(self):
        raw = {"predictions": {"percent": {"home": "n/a", "draw": "30%", "away": "20%"}}}
        assert ts._parse_apifb_prediction(raw, "A", "B", "2026-07-13") is None


class TestFilterApifbFixturesMatched:
    _BETARABIA = [
        {"fixture_id": "B1", "home_team": "Manchester United", "away_team": "Liverpool"},
        {"fixture_id": "B2", "home_team": "Real Madrid", "away_team": "Barcelona"},
    ]

    def test_keeps_only_fixtures_priced_by_betarabia(self):
        apifb = [
            {"fixture_id": 1, "home_team": "Manchester United", "away_team": "Liverpool"},
            {"fixture_id": 2, "home_team": "Some Obscure FC", "away_team": "Another Obscure FC"},
        ]
        matched = ts._filter_apifb_fixtures_matched(apifb, self._BETARABIA, limit=40)
        assert [m["fixture_id"] for m in matched] == [1]

    def test_respects_budget_cap(self):
        apifb = [
            {"fixture_id": i, "home_team": "Manchester United", "away_team": "Liverpool"}
            for i in range(5)
        ]
        matched = ts._filter_apifb_fixtures_matched(apifb, self._BETARABIA, limit=3)
        assert len(matched) == 3

    def test_empty_betarabia_returns_empty(self):
        apifb = [{"fixture_id": 1, "home_team": "Manchester United", "away_team": "Liverpool"}]
        assert ts._filter_apifb_fixtures_matched(apifb, [], limit=40) == []

    def test_empty_apifb_returns_empty(self):
        assert ts._filter_apifb_fixtures_matched([], self._BETARABIA, limit=40) == []


class TestGetApiFootballPredictions:
    def test_no_key_returns_empty_and_makes_no_calls(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ts, "_api_football_key", lambda base_dir=None: None)
        called = []
        monkeypatch.setattr(
            ts, "_fetch_apifb_fixtures", lambda *a, **k: called.append("fixtures") or []
        )
        preds = ts.get_api_football_predictions(
            "2026-07-13", odds_db=str(tmp_path / "missing.db")
        )
        assert preds == []
        assert called == []

    def test_no_betarabia_fixtures_short_circuits_before_network(self, monkeypatch, tmp_path):
        import sqlite3

        odds_db = str(tmp_path / "odds_stream.db")
        conn = sqlite3.connect(odds_db)
        conn.execute(
            "CREATE TABLE fixture (fixture_id TEXT, home_team TEXT, away_team TEXT, "
            "tournament_name TEXT, kickoff_time TEXT, kickoff_date TEXT)"
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(ts, "_api_football_key", lambda base_dir=None: "some-key")
        called = []
        monkeypatch.setattr(
            ts, "_fetch_apifb_fixtures", lambda *a, **k: called.append("fixtures") or []
        )
        preds = ts.get_api_football_predictions("2026-07-13", odds_db=odds_db)
        assert preds == []
        assert called == []

    @staticmethod
    def _seed_betarabia(tmp_path):
        import sqlite3

        odds_db = str(tmp_path / "odds_stream.db")
        conn = sqlite3.connect(odds_db)
        conn.execute(
            "CREATE TABLE fixture (fixture_id TEXT, home_team TEXT, away_team TEXT, "
            "tournament_name TEXT, kickoff_time TEXT, kickoff_date TEXT)"
        )
        conn.execute(
            "INSERT INTO fixture VALUES "
            "('B1','Manchester United','Liverpool','EPL','2026-07-13T18:00:00Z','2026-07-13')"
        )
        conn.commit()
        conn.close()
        return odds_db

    def test_fetches_and_parses_matched_fixture(self, monkeypatch, tmp_path):
        odds_db = self._seed_betarabia(tmp_path)
        ts._apifb_predictions_cache.clear()
        monkeypatch.setattr(ts, "_api_football_key", lambda base_dir=None: "key123")
        monkeypatch.setattr(
            ts,
            "_fetch_apifb_fixtures",
            lambda date_str, key: [
                {"fixture_id": 99, "home_team": "Manchester United", "away_team": "Liverpool"}
            ],
        )
        fetch_calls = []

        def fake_fetch_pred(fid, key):
            fetch_calls.append(fid)
            return {"predictions": {"percent": {"home": "60%", "draw": "25%", "away": "15%"}}}

        monkeypatch.setattr(ts, "_fetch_apifb_prediction", fake_fetch_pred)
        preds = ts.get_api_football_predictions("2026-07-13", odds_db=odds_db)
        assert len(preds) == 1
        assert preds[0]["source"] == "APIFB"
        assert preds[0]["predicted_side"] == "Home (1)"
        assert fetch_calls == [99]

    def test_caches_per_fixture_per_day_no_duplicate_fetch(self, monkeypatch, tmp_path):
        odds_db = self._seed_betarabia(tmp_path)
        ts._apifb_predictions_cache.clear()
        monkeypatch.setattr(ts, "_api_football_key", lambda base_dir=None: "key123")
        monkeypatch.setattr(
            ts,
            "_fetch_apifb_fixtures",
            lambda date_str, key: [
                {"fixture_id": 99, "home_team": "Manchester United", "away_team": "Liverpool"}
            ],
        )
        fetch_calls = []

        def fake_fetch_pred(fid, key):
            fetch_calls.append(fid)
            return {"predictions": {"percent": {"home": "60%", "draw": "25%", "away": "15%"}}}

        monkeypatch.setattr(ts, "_fetch_apifb_prediction", fake_fetch_pred)
        ts.get_api_football_predictions("2026-07-13", odds_db=odds_db)
        ts.get_api_football_predictions("2026-07-13", odds_db=odds_db)
        assert fetch_calls == [99]  # second call served entirely from cache

    def test_budget_cap_limits_prediction_fetches(self, monkeypatch, tmp_path):
        odds_db = self._seed_betarabia(tmp_path)
        ts._apifb_predictions_cache.clear()
        monkeypatch.setattr(ts, "_api_football_key", lambda base_dir=None: "key123")
        many_fixtures = [
            {"fixture_id": i, "home_team": "Manchester United", "away_team": "Liverpool"}
            for i in range(50)
        ]
        monkeypatch.setattr(ts, "_fetch_apifb_fixtures", lambda date_str, key: many_fixtures)
        fetch_calls = []

        def fake_fetch_pred(fid, key):
            fetch_calls.append(fid)
            return {"predictions": {"percent": {"home": "60%", "draw": "25%", "away": "15%"}}}

        monkeypatch.setattr(ts, "_fetch_apifb_prediction", fake_fetch_pred)
        preds = ts.get_api_football_predictions("2026-07-13", odds_db=odds_db)
        assert len(fetch_calls) <= ts._APIFB_MAX_PER_DAY
        assert len(preds) <= ts._APIFB_MAX_PER_DAY
        assert len(fetch_calls) < len(many_fixtures)  # budget actually capped it


class TestGetAllTipsterPredictionsIncludesApifb:
    def test_includes_apifb_predictions_in_combined_list(self, monkeypatch):
        monkeypatch.setattr(ts, "get_forebet_predictions", lambda date_str: [])
        monkeypatch.setattr(ts, "get_soccerpunter_predictions", lambda date_str: [])
        monkeypatch.setattr(ts, "get_predictz_predictions", lambda date_str: [])
        monkeypatch.setattr(
            ts,
            "get_api_football_predictions",
            lambda date_str: [
                {
                    "home_team": "A",
                    "away_team": "B",
                    "source": "APIFB",
                    "predicted_side": "Home (1)",
                    "confidence": 60.0,
                    "predicted_ou": None,
                    "date": date_str,
                }
            ],
        )
        preds = ts.get_all_tipster_predictions("2026-07-13")
        assert any(p["source"] == "APIFB" for p in preds)

    def test_apifb_error_does_not_break_other_sources(self, monkeypatch):
        monkeypatch.setattr(
            ts,
            "get_forebet_predictions",
            lambda date_str: [
                {
                    "home_team": "X",
                    "away_team": "Y",
                    "source": "FOREBET",
                    "predicted_side": "Home (1)",
                    "confidence": 50.0,
                    "predicted_ou": None,
                    "date": date_str,
                }
            ],
        )
        monkeypatch.setattr(ts, "get_soccerpunter_predictions", lambda date_str: [])
        monkeypatch.setattr(ts, "get_predictz_predictions", lambda date_str: [])

        def boom(date_str):
            raise RuntimeError("APIFB down")

        monkeypatch.setattr(ts, "get_api_football_predictions", boom)
        preds = ts.get_all_tipster_predictions("2026-07-13")
        assert len(preds) == 1
        assert preds[0]["source"] == "FOREBET"


class TestPlacementApifbBypassesRealBankroll:
    """CRITICAL (see CLAUDE.md): only source=='FOREBET' may touch
    real_bankroll.db. APIFB is a pure paper research track and must never
    reach that gate."""

    _BET_LOG_SCHEMA = TestPlacementSkipsInPlay._BET_LOG_SCHEMA

    def _setup(self, tmp_path):
        import sqlite3

        odds_db = str(tmp_path / "odds_stream.db")
        bet_db = str(tmp_path / "bet_log.db")
        far_future = "2026-12-31T23:00:00.000Z"
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
            [("F1", "Alpha City", "Beta United", "NPL", far_future, "2026-12-31")],
        )
        oc.executemany(
            "INSERT INTO market VALUES (?,?,?,?)",
            [("F1", "Match Result", "Home", 1.8)],
        )
        oc.commit()
        oc.close()
        sqlite3.connect(bet_db).executescript(self._BET_LOG_SCHEMA)
        return odds_db, bet_db

    def test_apifb_bet_inserted_with_correct_source_and_no_real_bankroll_gate(
        self, tmp_path, monkeypatch
    ):
        import sqlite3

        odds_db, bet_db = self._setup(tmp_path)
        monkeypatch.setattr(ts, "_paper_balance", lambda: 1000.0)

        def _boom_real_register_bet(*a, **k):
            raise AssertionError("APIFB bet must never touch the real bankroll gate")

        monkeypatch.setattr(
            "src.bankroll_tracker.register_bet", _boom_real_register_bet, raising=False
        )

        predictions = [
            {
                "home_team": "Alpha City",
                "away_team": "Beta United",
                "source": "APIFB",
                "predicted_side": "Home (1)",
                "confidence": 60.0,
            }
        ]
        placed = ts.place_tipster_bets(predictions, bet_db=bet_db, odds_db=odds_db)

        conn = sqlite3.connect(bet_db)
        row = conn.execute("SELECT bet_source, fixture_id FROM bet_log").fetchone()
        conn.close()
        assert placed == 1
        assert row[0] == "TIPSTER_APIFB"
        assert row[1] == "F1"


class TestNationLeagueLookup:
    """lookup_nation_league(): resolve a bet's nation+league from the
    persisted API-Football fixtures metadata (captured at zero extra quota)."""

    def _write_meta(self, base, fixtures):
        import json, os
        os.makedirs(os.path.join(base, "data"), exist_ok=True)
        with open(os.path.join(base, "data", "apifb_fixture_meta.json"), "w") as f:
            json.dump({"fixtures": fixtures}, f)

    def test_lookup_finds_nation_and_league(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ts, "BASE_DIR", str(tmp_path))
        self._write_meta(str(tmp_path), [
            {"home": "Djurgardens IF", "away": "Halmstads BK",
             "league": "Allsvenskan", "country": "Sweden"},
        ])
        assert ts.lookup_nation_league("Djurgarden", "Halmstad") == ("Sweden", "Allsvenskan")

    def test_lookup_returns_none_when_no_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ts, "BASE_DIR", str(tmp_path))
        self._write_meta(str(tmp_path), [
            {"home": "Real Madrid", "away": "Barcelona",
             "league": "La Liga", "country": "Spain"},
        ])
        assert ts.lookup_nation_league("Djurgarden", "Halmstad") is None

    def test_lookup_missing_file_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ts, "BASE_DIR", str(tmp_path))
        assert ts.lookup_nation_league("A", "B") is None


class TestConsensusStrategy:
    """Mix strategy (2026-07-14): a CONSENSUS pick exists only where FOREBET
    and APIFB independently agree on the same side of the same fixture
    (fuzzy team matching — the two sources name teams differently). Placed as
    bet_source='TIPSTER_CONSENSUS', research ledger only."""

    def _preds(self, fb_side="Home (1)", af_side="Home (1)", af_home="Djurgardens IF", af_away="Halmstads BK"):
        return [
            {"home_team": "Djurgarden", "away_team": "Halmstad", "source": "FOREBET",
             "predicted_side": fb_side, "confidence": 60.0, "predicted_ou": "Over 2.5",
             "ou_confidence": 58.0},
            {"home_team": af_home, "away_team": af_away, "source": "APIFB",
             "predicted_side": af_side, "confidence": 70.0, "predicted_ou": "Over 2.5",
             "ou_confidence": 62.0},
        ]

    def test_agreement_produces_consensus_with_averaged_confidence(self):
        cons = ts.build_consensus_predictions(self._preds())
        assert len(cons) == 1
        c = cons[0]
        assert c["source"] == "CONSENSUS"
        assert c["predicted_side"] == "Home (1)"
        assert c["confidence"] == pytest.approx(65.0)  # mean of 60 and 70
        assert c["predicted_ou"] == "Over 2.5"          # O/U agreement too
        assert c["ou_confidence"] == pytest.approx(60.0)

    def test_disagreement_produces_nothing(self):
        assert ts.build_consensus_predictions(self._preds(af_side="Away (2)")) == []

    def test_different_fixtures_do_not_pair(self):
        assert ts.build_consensus_predictions(
            self._preds(af_home="Real Madrid", af_away="Barcelona")) == []

    def test_ou_disagreement_drops_ou_but_keeps_1x2(self):
        preds = self._preds()
        preds[1]["predicted_ou"] = "Under 2.5"
        cons = ts.build_consensus_predictions(preds)
        assert len(cons) == 1
        assert cons[0]["predicted_side"] == "Home (1)"
        assert cons[0]["predicted_ou"] is None

    def test_consensus_places_as_tipster_consensus(self, tmp_path, monkeypatch):
        import sqlite3
        odds_db, bet_db = TestPlacementSkipsInPlay()._setup(tmp_path)
        monkeypatch.setattr(ts, "_paper_balance", lambda: 1000.0)
        monkeypatch.setattr(ts, "_allowed_tipster_sources", lambda: {"CONSENSUS"})
        preds = [
            {"home_team": "Alpha City", "away_team": "Beta United", "source": "FOREBET",
             "predicted_side": "Home (1)", "confidence": 60.0},
            {"home_team": "Alpha City FC", "away_team": "Beta Utd", "source": "APIFB",
             "predicted_side": "Home (1)", "confidence": 70.0},
        ]
        all_preds = preds + ts.build_consensus_predictions(preds)
        placed = ts.place_tipster_bets(all_preds, bet_db=bet_db, odds_db=odds_db)
        conn = sqlite3.connect(bet_db)
        sources = {r[0] for r in conn.execute("SELECT bet_source FROM bet_log")}
        conn.close()
        assert sources == {"TIPSTER_CONSENSUS"}
        assert placed == 1
