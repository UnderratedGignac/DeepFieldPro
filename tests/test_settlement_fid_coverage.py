"""The coverage cliff itself: a fixture must stay resolvable by id across days.

Before the durable store, settle_open_bets() could only resolve a fixture by id
while it was still in today's dashboard state. Measured fid-direct rate by
settle lag: 14.9% same-day, 5.7% at +1 day, 0.0% from +2 days on. These tests
pin the fix at the level that matters — a result harvested on day 1 is still
resolvable on day 5, which is inside the 7-day settlement lookback.
"""

import importlib

import pytest

fr = importlib.import_module("src.fixture_results")


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "completed_fixtures.db")
    fr.ensure_fixture_results(p)
    return p


def _dash(fid, ns, hs, aws, status="FT"):
    return [
        {
            "fixture_id": fid,
            "fixture_ns": ns,
            "fixture": {"status": {"short": status}, "home_score": hs, "away_score": aws},
        }
    ]


def test_result_survives_after_the_fixture_leaves_todays_state(db):
    """The exact regression: harvest today, still resolvable days later."""
    fr.record_results(db, fr.rows_from_dashboard_state(_dash("16512229", fr.NS_SOFASCORE, 2, 1)))

    # Later cycles: dashboard state has rolled over and no longer holds it.
    fr.record_results(db, fr.rows_from_dashboard_state([]))

    assert fr.load_flat_scores(db)["16512229"] == (2, 1)
    assert fr.load_scores(db)[(fr.NS_SOFASCORE, "16512229")] == (2, 1)


def test_whole_settlement_lookback_is_covered(db):
    """settle_open_bets() looks back up to 7 days — all of it must resolve."""
    for day in range(8):
        fr.record_results(
            db,
            fr.rows_from_sofascore_events(
                {f"d-{day}": [{"id": 20000 + day, "status": {"type": "finished"},
                               "homeScore": {"current": day}, "awayScore": {"current": 0}}]}
            ),
        )
    flat = fr.load_flat_scores(db)
    for day in range(8):
        assert flat[str(20000 + day)] == (day, 0)


def test_betarabia_namespace_is_resolvable_once_ids_are_real(db):
    """Betarabia bets sat at 0.0% fid-direct because the builders minted md5s.
    With the real Kickertech id stamped, they resolve like any other."""
    fr.record_results(db, fr.rows_from_dashboard_state(_dash("28647082", fr.NS_BETARABIA, 1, 3)))
    assert fr.load_scores(db)[(fr.NS_BETARABIA, "28647082")] == (1, 3)


def test_a_bet_is_never_graded_off_a_foreign_namespace(db):
    """Two sources reusing one integer must not cross-grade — the failure mode
    behind the River Plate Reserves mis-grade."""
    fr.record_results(
        db,
        [
            (fr.NS_SOFASCORE, "999", 5, 0, "FT"),
            (fr.NS_BETARABIA, "999", 0, 5, "FT"),
        ],
    )
    scores = fr.load_scores(db)
    assert scores[(fr.NS_SOFASCORE, "999")] == (5, 0)
    assert scores[(fr.NS_BETARABIA, "999")] == (0, 5)
    # A legacy bet with only "999" and no namespace must get NOTHING, not a coin flip.
    assert "999" not in fr.load_flat_scores(db)


def test_unfinished_fixture_never_becomes_a_grade(db):
    """An in-play score must never settle a bet."""
    fr.record_results(db, fr.rows_from_dashboard_state(_dash("5", fr.NS_SOFASCORE, 1, 0, status="1H")))
    assert fr.load_flat_scores(db) == {}


def test_corrected_score_replaces_the_earlier_one(db):
    """A provisional score later corrected must not leave two conflicting rows."""
    fr.record_results(db, fr.rows_from_dashboard_state(_dash("77", fr.NS_SOFASCORE, 1, 0)))
    fr.record_results(db, fr.rows_from_dashboard_state(_dash("77", fr.NS_SOFASCORE, 1, 2)))
    assert fr.load_flat_scores(db)["77"] == (1, 2)
