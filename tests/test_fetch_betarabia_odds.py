"""Unit tests for the Betarabia fixture-metadata fallback chain.

Covers:
- fetch_betarabia_odds() in src/live_predictions_daemon.py — reads
  odds_stream.db `fixture` rows into a dict keyed "Home vs Away" carrying
  {kickoff, league, status}.
- _betarabia_fixture_fallback() in src/free_scraper_module.py — turns that
  metadata into daemon-shaped fixture dicts. Regression guard for the
  documented bug where the fallback stamped now()/'NS'/'Betarabia' on every
  fixture instead of the real scraped kickoff/league/status.

All DBs are tmp_path sqlite files; DATA_DIR is monkeypatched. No network.
"""

import datetime
import sqlite3

import pytest

from tests._daemon_test_utils import import_daemon

lpd = import_daemon()

import src.free_scraper_module as fsm  # noqa: E402  (after guarded daemon import)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_odds_stream_db(data_dir, rows):
    """Create data_dir/odds_stream.db with a `fixture` table.

    rows: iterable of (fixture_id, home, away, kickoff_time, tournament_name,
                       scraped_at)
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "odds_stream.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE fixture (
               fixture_id      TEXT,
               home_team       TEXT,
               away_team       TEXT,
               kickoff_time    TEXT,
               kickoff_date    TEXT,
               league_id       TEXT,
               tournament_name TEXT,
               scraped_at      TEXT
           )"""
    )
    conn.executemany(
        "INSERT INTO fixture (fixture_id, home_team, away_team, kickoff_time,"
        " tournament_name, scraped_at) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


FUTURE_KO = "2099-01-01T18:30:00.000Z"
PAST_KO = "2020-01-01T18:30:00.000Z"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    return d


# ---------------------------------------------------------------------------
# fetch_betarabia_odds()
# ---------------------------------------------------------------------------

class TestFetchBetarabiaOdds:
    def test_missing_db_returns_empty_dict_and_none(self, data_dir):
        matches, raw = lpd.fetch_betarabia_odds()
        assert matches == {}
        assert raw is None

    def test_keys_are_home_vs_away(self, data_dir):
        _make_odds_stream_db(
            data_dir,
            [("f1", "Arsenal", "Chelsea", FUTURE_KO, "Premier League", "2026-07-10T00:00:00Z")],
        )
        matches, raw = lpd.fetch_betarabia_odds()
        assert list(matches.keys()) == ["Arsenal vs Chelsea"]
        assert raw is None

    def test_metadata_comes_from_db_not_now(self, data_dir):
        """Regression guard: kickoff must be the DB value, never the scrape time."""
        _make_odds_stream_db(
            data_dir,
            [("f1", "Arsenal", "Chelsea", FUTURE_KO, "Premier League", "x")],
        )
        matches, _ = lpd.fetch_betarabia_odds()
        info = matches["Arsenal vs Chelsea"]
        # Z-suffixed ISO is normalised to +00:00, .000 microseconds dropped
        assert info["kickoff"] == "2099-01-01T18:30:00+00:00"
        assert info["league"] == "Premier League"
        # Not stamped with "now": parse back and confirm it's the far future
        ko = datetime.datetime.fromisoformat(info["kickoff"])
        now = datetime.datetime.now(datetime.timezone.utc)
        assert (ko - now).days > 300

    def test_future_kickoff_status_ns(self, data_dir):
        _make_odds_stream_db(data_dir, [("f1", "A", "B", FUTURE_KO, "L", "x")])
        matches, _ = lpd.fetch_betarabia_odds()
        assert matches["A vs B"]["status"] == "NS"

    def test_past_kickoff_marked_ft(self, data_dir):
        _make_odds_stream_db(data_dir, [("f1", "A", "B", PAST_KO, "L", "x")])
        matches, _ = lpd.fetch_betarabia_odds()
        assert matches["A vs B"]["status"] == "FT"

    def test_null_tournament_falls_back_to_betarabia_label(self, data_dir):
        _make_odds_stream_db(data_dir, [("f1", "A", "B", FUTURE_KO, None, "x")])
        matches, _ = lpd.fetch_betarabia_odds()
        assert matches["A vs B"]["league"] == "Betarabia"

    def test_rows_with_missing_team_names_are_skipped(self, data_dir):
        _make_odds_stream_db(
            data_dir,
            [
                ("f1", None, "B", FUTURE_KO, "L", "x"),
                ("f2", "A", None, FUTURE_KO, "L", "x"),
                ("f3", "", "B", FUTURE_KO, "L", "x"),
                ("f4", "Home", "Away", FUTURE_KO, "L", "x"),
            ],
        )
        matches, _ = lpd.fetch_betarabia_odds()
        assert list(matches.keys()) == ["Home vs Away"]

    def test_unparseable_kickoff_gives_none_and_ns(self, data_dir):
        _make_odds_stream_db(data_dir, [("f1", "A", "B", "not-a-date", "L", "x")])
        matches, _ = lpd.fetch_betarabia_odds()
        assert matches["A vs B"]["kickoff"] is None
        assert matches["A vs B"]["status"] == "NS"

    def test_null_kickoff_gives_none_and_ns(self, data_dir):
        _make_odds_stream_db(data_dir, [("f1", "A", "B", None, "L", "x")])
        matches, _ = lpd.fetch_betarabia_odds()
        assert matches["A vs B"]["kickoff"] is None
        assert matches["A vs B"]["status"] == "NS"

    def test_naive_kickoff_assumed_utc(self, data_dir):
        _make_odds_stream_db(
            data_dir, [("f1", "A", "B", "2099-01-01T18:30:00", "L", "x")]
        )
        matches, _ = lpd.fetch_betarabia_odds()
        assert matches["A vs B"]["kickoff"] == "2099-01-01T18:30:00+00:00"


# ---------------------------------------------------------------------------
# _betarabia_fixture_fallback() — free_scraper_module fallback builder
# ---------------------------------------------------------------------------

class TestBetarabiaFixtureFallback:
    def test_uses_real_metadata_not_now_ns_betarabia(self, monkeypatch):
        """THE regression guard: when metadata exists, the builder must carry it
        through — not stamp now()/'NS'/'Betarabia' (the documented glitch where
        all kickoffs showed the scrape time)."""
        meta = {
            "Arsenal vs Chelsea": {
                "kickoff": "2099-01-01T18:30:00+00:00",
                "league": "Premier League",
                "status": "FT",
            }
        }
        monkeypatch.setattr(lpd, "fetch_betarabia_odds", lambda: (meta, None))
        fixtures = fsm._betarabia_fixture_fallback()
        assert len(fixtures) == 1
        f = fixtures[0]
        assert f["fixture"]["date"] == "2099-01-01T18:30:00+00:00"
        assert f["fixture"]["status"]["short"] == "FT"
        assert f["league"]["name"] == "Premier League"
        assert f["teams"]["home"]["name"] == "Arsenal"
        assert f["teams"]["away"]["name"] == "Chelsea"
        # date really is the metadata kickoff, nowhere near "now"
        ko = datetime.datetime.fromisoformat(f["fixture"]["date"])
        now = datetime.datetime.now(datetime.timezone.utc)
        assert (ko - now).days > 300

    def test_defaults_apply_only_when_metadata_missing(self, monkeypatch):
        """When the scraper provides no kickoff/league/status the documented
        defaults (now-ish date, NS, Betarabia) kick in."""
        meta = {"A vs B": {"kickoff": None, "league": None, "status": None}}
        monkeypatch.setattr(lpd, "fetch_betarabia_odds", lambda: (meta, None))
        before = datetime.datetime.now(datetime.timezone.utc)
        fixtures = fsm._betarabia_fixture_fallback()
        after = datetime.datetime.now(datetime.timezone.utc)
        f = fixtures[0]
        assert f["fixture"]["status"]["short"] == "NS"
        assert f["league"]["name"] == "Betarabia"
        stamped = datetime.datetime.fromisoformat(f["fixture"]["date"])
        assert before <= stamped <= after

    def test_names_without_vs_are_skipped(self, monkeypatch):
        meta = {"NotAMatchName": {"kickoff": None, "league": "L", "status": "NS"}}
        monkeypatch.setattr(lpd, "fetch_betarabia_odds", lambda: (meta, None))
        assert fsm._betarabia_fixture_fallback() == []

    def test_fixture_id_is_deterministic(self, monkeypatch):
        meta = {"A vs B": {"kickoff": None, "league": "L", "status": "NS"}}
        monkeypatch.setattr(lpd, "fetch_betarabia_odds", lambda: (meta, None))
        fid1 = fsm._betarabia_fixture_fallback()[0]["fixture"]["id"]
        fid2 = fsm._betarabia_fixture_fallback()[0]["fixture"]["id"]
        assert fid1 == fid2
        assert 0 <= fid1 < 100000000

    def test_fetch_error_yields_empty_list(self, monkeypatch):
        def _boom():
            raise RuntimeError("db exploded")

        monkeypatch.setattr(lpd, "fetch_betarabia_odds", _boom)
        assert fsm._betarabia_fixture_fallback() == []

    def test_no_live_scores_in_fallback_fixtures(self, monkeypatch):
        meta = {"A vs B": {"kickoff": None, "league": "L", "status": "NS"}}
        monkeypatch.setattr(lpd, "fetch_betarabia_odds", lambda: (meta, None))
        f = fsm._betarabia_fixture_fallback()[0]
        assert f["fixture"]["home_score"] is None
        assert f["fixture"]["away_score"] is None
