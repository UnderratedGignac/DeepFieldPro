"""Durable fixture_id -> score store.

settle_open_bets() built its direct-lookup index (_fid_to_score) from a single
volatile file, data/todays_dashboard_state.json, which is rewritten every cycle
with only TODAY's fixtures. Settlement looks back up to 7 days, so the index had
already forgotten the fixture by the time most bets settled:

    settled same day  14.9% fid-direct
    settled +1 day     5.7%
    settled +2 days    0.0%   <- falls off a cliff
    settled +3 days    0.0%

Only 11.8% of verified settles were graded by fixture id; the rest fell through
to fuzzy team-name matching, which the 2026-07-12 audit showed gets ~29% of
externally-checkable grades wrong.

This module persists results keyed by (namespace, fixture_id) so the index
survives across cycles and dates. Namespacing matters because fixture ids come
from several sources (Sofascore 14-17M, Betarabia/Kickertech 27-29M, ESPN
4xxxxxxxx, plus synthetic md5 ids) that must never be joined to each other.
"""

import importlib
import time

import pytest

fr = importlib.import_module("src.fixture_results")


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "completed_fixtures.db")
    fr.ensure_fixture_results(p)
    return p


# ---------------------------------------------------------------------------
# schema / basic round-trip
# ---------------------------------------------------------------------------


def test_ensure_is_idempotent(db):
    fr.ensure_fixture_results(db)
    fr.ensure_fixture_results(db)  # must not raise


def test_record_then_load(db):
    fr.record_results(db, [(fr.NS_SOFASCORE, "16512229", 2, 1, "FT")])
    scores = fr.load_scores(db)
    assert scores[(fr.NS_SOFASCORE, "16512229")] == (2, 1)


def test_record_returns_written_count(db):
    n = fr.record_results(
        db,
        [
            (fr.NS_SOFASCORE, "1", 0, 0, "FT"),
            (fr.NS_SOFASCORE, "2", 3, 1, "FT"),
        ],
    )
    assert n == 2


def test_record_of_empty_is_a_noop(db):
    assert fr.record_results(db, []) == 0


def test_fixture_id_is_stored_as_text(db):
    """Callers pass ints and strings interchangeably; lookups must still hit."""
    fr.record_results(db, [(fr.NS_SOFASCORE, 16512229, 2, 1, "FT")])
    assert fr.load_scores(db)[(fr.NS_SOFASCORE, "16512229")] == (2, 1)


def test_later_write_wins(db):
    """A corrected score must overwrite an earlier one, not duplicate it."""
    fr.record_results(db, [(fr.NS_SOFASCORE, "9", 1, 1, "FT")])
    fr.record_results(db, [(fr.NS_SOFASCORE, "9", 2, 1, "FT")])
    scores = fr.load_scores(db)
    assert scores[(fr.NS_SOFASCORE, "9")] == (2, 1)
    assert len([k for k in scores if k[1] == "9"]) == 1


def test_rows_with_missing_scores_are_skipped(db):
    n = fr.record_results(
        db,
        [
            (fr.NS_SOFASCORE, "1", None, 1, "FT"),
            (fr.NS_SOFASCORE, "2", 1, None, "FT"),
            (fr.NS_SOFASCORE, "3", 1, 0, "FT"),
        ],
    )
    assert n == 1
    assert list(fr.load_scores(db)) == [(fr.NS_SOFASCORE, "3")]


def test_rows_with_no_fixture_id_are_skipped(db):
    assert fr.record_results(db, [(fr.NS_SOFASCORE, None, 1, 0, "FT")]) == 0


def test_unfinished_fixtures_are_not_stored(db):
    """Only final results may be used to grade a bet."""
    n = fr.record_results(
        db,
        [
            (fr.NS_SOFASCORE, "1", 1, 0, "inprogress"),
            (fr.NS_SOFASCORE, "2", 1, 0, "FT"),
        ],
    )
    assert n == 1
    assert list(fr.load_scores(db)) == [(fr.NS_SOFASCORE, "2")]


# ---------------------------------------------------------------------------
# namespacing — the thing that stops cross-source id collisions
# ---------------------------------------------------------------------------


def test_same_id_in_two_namespaces_stays_separate(db):
    fr.record_results(
        db,
        [
            (fr.NS_SOFASCORE, "12345", 1, 0, "FT"),
            (fr.NS_BETARABIA, "12345", 3, 3, "FT"),
        ],
    )
    scores = fr.load_scores(db)
    assert scores[(fr.NS_SOFASCORE, "12345")] == (1, 0)
    assert scores[(fr.NS_BETARABIA, "12345")] == (3, 3)


def test_flat_map_serves_legacy_bets_without_a_namespace(db):
    """Bets placed before namespace stamping have only a bare fixture_id."""
    fr.record_results(db, [(fr.NS_SOFASCORE, "777", 2, 2, "FT")])
    assert fr.load_flat_scores(db)["777"] == (2, 2)


def test_flat_map_drops_ambiguous_ids(db):
    """If one id means different results in two namespaces, a legacy bet
    carrying only that id cannot be graded safely — it must be omitted."""
    fr.record_results(
        db,
        [
            (fr.NS_SOFASCORE, "555", 1, 0, "FT"),
            (fr.NS_BETARABIA, "555", 0, 4, "FT"),
        ],
    )
    assert "555" not in fr.load_flat_scores(db)


def test_flat_map_keeps_ids_that_agree_across_namespaces(db):
    fr.record_results(
        db,
        [
            (fr.NS_SOFASCORE, "556", 1, 0, "FT"),
            (fr.NS_BETARABIA, "556", 1, 0, "FT"),
        ],
    )
    assert fr.load_flat_scores(db)["556"] == (1, 0)


# ---------------------------------------------------------------------------
# retention window
# ---------------------------------------------------------------------------


def test_load_respects_the_lookback_window(db):
    old = time.time() - 40 * 86400
    fr.record_results(db, [(fr.NS_SOFASCORE, "old", 1, 0, "FT")], seen_at=old)
    fr.record_results(db, [(fr.NS_SOFASCORE, "new", 2, 0, "FT")])
    keys = set(fr.load_scores(db, days=14))
    assert (fr.NS_SOFASCORE, "new") in keys
    assert (fr.NS_SOFASCORE, "old") not in keys


def test_load_with_no_window_returns_everything(db):
    old = time.time() - 400 * 86400
    fr.record_results(db, [(fr.NS_SOFASCORE, "ancient", 1, 0, "FT")], seen_at=old)
    assert (fr.NS_SOFASCORE, "ancient") in fr.load_scores(db, days=None)


def test_purge_drops_rows_past_retention(db):
    old = time.time() - 90 * 86400
    fr.record_results(db, [(fr.NS_SOFASCORE, "old", 1, 0, "FT")], seen_at=old)
    fr.record_results(db, [(fr.NS_SOFASCORE, "keep", 1, 0, "FT")])
    assert fr.purge_fixture_results(db, days=30) == 1
    assert set(fr.load_scores(db, days=None)) == {(fr.NS_SOFASCORE, "keep")}


def test_default_retention_spans_the_settlement_lookback(db):
    """settle_open_bets() looks back up to 7 days."""
    assert fr.FIXTURE_RESULTS_RETENTION_DAYS >= 14


# ---------------------------------------------------------------------------
# robustness — settlement must never be broken by this module
# ---------------------------------------------------------------------------


def test_load_on_missing_db_returns_empty(tmp_path):
    assert fr.load_scores(str(tmp_path / "nope.db")) == {}
    assert fr.load_flat_scores(str(tmp_path / "nope.db")) == {}


def test_record_on_unwritable_path_does_not_raise(tmp_path):
    bad = str(tmp_path / "no_such_dir" / "x.db")
    assert fr.record_results(bad, [(fr.NS_SOFASCORE, "1", 1, 0, "FT")]) == 0


def test_purge_on_missing_db_returns_zero(tmp_path):
    assert fr.purge_fixture_results(str(tmp_path / "nope.db")) == 0


# ---------------------------------------------------------------------------
# harvesters — turning the daemon's existing sources into rows
# ---------------------------------------------------------------------------


def test_dashboard_rows_keep_only_finished_with_scores(db):
    state = [
        {"fixture_id": "1", "fixture": {"status": {"short": "FT"}, "home_score": 2, "away_score": 1}},
        {"fixture_id": "2", "fixture": {"status": {"short": "NS"}, "home_score": None, "away_score": None}},
        {"fixture_id": "3", "fixture": {"status": {"short": "1H"}, "home_score": 1, "away_score": 0}},
    ]
    assert fr.record_results(db, fr.rows_from_dashboard_state(state)) == 1
    assert fr.load_flat_scores(db)["1"] == (2, 1)


def test_dashboard_rows_use_stamped_namespace_when_present(db):
    state = [{
        "fixture_id": "77", "fixture_ns": fr.NS_BETARABIA,
        "fixture": {"status": {"short": "FT"}, "home_score": 0, "away_score": 0},
    }]
    fr.record_results(db, fr.rows_from_dashboard_state(state))
    assert (fr.NS_BETARABIA, "77") in fr.load_scores(db)


def test_dashboard_rows_fall_back_to_unknown_namespace(db):
    state = [{"fixture_id": "88", "fixture": {"status": {"short": "FT"}, "home_score": 1, "away_score": 1}}]
    fr.record_results(db, fr.rows_from_dashboard_state(state))
    assert (fr.NS_UNKNOWN, "88") in fr.load_scores(db)


def test_dashboard_rows_tolerate_junk(db):
    assert fr.rows_from_dashboard_state(None) == []
    assert fr.record_results(db, fr.rows_from_dashboard_state(["nope", 5, {}])) == 0


def test_sofascore_events_become_sofascore_namespace_rows(db):
    events = {"2026-08-20": [
        {"id": 16512229, "status": {"type": "finished"},
         "homeScore": {"current": 3}, "awayScore": {"current": 0}},
        {"id": 16512230, "status": {"type": "inprogress"},
         "homeScore": {"current": 1}, "awayScore": {"current": 1}},
    ]}
    assert fr.record_results(db, fr.rows_from_sofascore_events(events)) == 1
    assert fr.load_scores(db)[(fr.NS_SOFASCORE, "16512229")] == (3, 0)


def test_sofascore_harvest_spans_every_date_in_the_window(db):
    """The coverage cliff was 'today only' — this must cover the whole lookback."""
    events = {
        f"2026-08-{d:02d}": [
            {"id": 1000 + d, "status": {"type": "finished"},
             "homeScore": {"current": 1}, "awayScore": {"current": 0}}
        ]
        for d in range(11, 19)
    }
    assert fr.record_results(db, fr.rows_from_sofascore_events(events)) == 8


def test_sofascore_harvest_accepts_a_bare_list(db):
    events = [{"id": 5, "status": {"type": "finished"},
               "homeScore": {"current": 2}, "awayScore": {"current": 2}}]
    assert fr.record_results(db, fr.rows_from_sofascore_events(events)) == 1


def test_sofascore_harvest_tolerates_junk(db):
    assert fr.rows_from_sofascore_events(None) == []
    assert fr.record_results(db, fr.rows_from_sofascore_events({"d": ["x", None]})) == 0
