"""Settlement verification tests.

Most bets are graded by fuzzy NAME matching, not by fixture id, and not
because the id is missing. The namespaced result simply arrives too late:

    match ends              ~17:20Z
    fast feeds publish      ~17:2xZ   (Flashscore / ESPN / API-Football)
    settlement grades it     17:27Z   -> falls through to name-match
    Sofascore fid row lands  18:11Z   -> 44 minutes too late

The fast feeds carry no Sofascore ids, so they can only ever grade by name;
the only namespaced source rides a 30-minute cache. fid-direct therefore
never gets to grade a promptly-finishing match, and the two paths end up
grading different league populations (205 vs 69), which is why the recorded
-19.6% / +45% ROI split between them cannot be read as pure grading quality.

This module turns that lag into a measurement instead of a race: once the
namespaced result does arrive, re-derive the grade and compare it with what
was actually recorded. That answers the question the confound note could
not — how often is name-match actually WRONG?

Two properties matter most and are pinned here:
  * it reuses tools.score_lookup._grade_bet, so a disagreement can only mean
    a real mis-grade and never a re-implementation bug;
  * it is strictly non-destructive — it never edits bet_log.result.
"""

import importlib
import sqlite3

import pytest


@pytest.fixture
def dbs(tmp_path):
    """A bet_log.db and a completed_fixtures.db wired for the verifier."""
    bet_db = tmp_path / "bet_log.db"
    fx_db = tmp_path / "completed_fixtures.db"

    conn = sqlite3.connect(bet_db)
    conn.execute(
        """CREATE TABLE bet_log (
               bet_id TEXT PRIMARY KEY, match_id TEXT, market_type TEXT, side TEXT,
               entry_odds REAL, stake REAL, result TEXT, pnl REAL,
               settle_source TEXT, fixture_id TEXT, fixture_ns TEXT, league TEXT
           )"""
    )
    conn.commit()
    conn.close()

    fx = importlib.import_module("src.fixture_results")
    fx.ensure_fixture_results(str(fx_db))
    return str(bet_db), str(fx_db)


def _add_bet(bet_db, bet_id, market, side, result, fid, ns, source="name-match"):
    conn = sqlite3.connect(bet_db)
    conn.execute(
        "INSERT INTO bet_log (bet_id, match_id, market_type, side, entry_odds, stake,"
        " result, pnl, settle_source, fixture_id, fixture_ns, league)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (bet_id, "A vs B", market, side, 2.0, 1.0, result, 0.0, source, fid, ns, "L"),
    )
    conn.commit()
    conn.close()


def _add_result(fx_db, ns, fid, hs, aws):
    fx = importlib.import_module("src.fixture_results")
    fx.record_results(fx_db, [(ns, str(fid), hs, aws, "FT")])


@pytest.fixture
def verifier():
    return importlib.import_module("src.settlement_verifier")


def test_agreeing_grade_is_recorded_as_agreement(dbs, verifier):
    bet_db, fx_db = dbs
    # 1-1 => BTTS Yes wins, and the bet was recorded W. They agree.
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore")
    _add_result(fx_db, "sofascore", "16881963", 1, 1)

    summary = verifier.verify_settlements(bet_db, fx_db)
    assert summary["checked"] == 1
    assert summary["agreed"] == 1
    assert summary["disagreed"] == 0


def test_disagreeing_grade_is_flagged(dbs, verifier):
    bet_db, fx_db = dbs
    # 1-0 => BTTS Yes LOSES, but the bet was recorded W. That is a mis-grade.
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore")
    _add_result(fx_db, "sofascore", "16881963", 1, 0)

    summary = verifier.verify_settlements(bet_db, fx_db)
    assert summary["disagreed"] == 1

    rows = verifier.load_disagreements(bet_db)
    assert len(rows) == 1
    assert rows[0]["bet_id"] == "b1"
    assert rows[0]["recorded_result"] == "W"
    assert rows[0]["fid_result"] == "L"
    assert rows[0]["home_score"] == 1 and rows[0]["away_score"] == 0


def test_never_modifies_the_original_bet(dbs, verifier):
    """Non-destructive: verification records, it does not re-grade."""
    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore")
    _add_result(fx_db, "sofascore", "16881963", 1, 0)  # says it should be L

    verifier.verify_settlements(bet_db, fx_db)

    conn = sqlite3.connect(bet_db)
    row = conn.execute(
        "SELECT result, pnl, settle_source FROM bet_log WHERE bet_id='b1'"
    ).fetchone()
    conn.close()
    assert row[0] == "W", "verification must never rewrite bet_log.result"
    assert row[2] == "name-match", "verification must never rewrite settle_source"


def test_fid_direct_bets_are_skipped(dbs, verifier):
    """Already graded off the namespaced id — nothing to cross-check."""
    bet_db, fx_db = dbs
    _add_bet(
        bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore", source="fid-direct"
    )
    _add_result(fx_db, "sofascore", "16881963", 1, 1)
    assert verifier.verify_settlements(bet_db, fx_db)["checked"] == 0


def test_bet_without_namespace_is_skipped(dbs, verifier):
    """No namespace means no trustworthy id join — that is the other known gap."""
    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", None)
    _add_result(fx_db, "sofascore", "16881963", 1, 1)
    assert verifier.verify_settlements(bet_db, fx_db)["checked"] == 0


def test_bet_with_no_namespaced_result_yet_is_skipped(dbs, verifier):
    """The 44-minute lag case: not yet verifiable is NOT a disagreement."""
    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore")
    summary = verifier.verify_settlements(bet_db, fx_db)
    assert summary["checked"] == 0
    assert summary["disagreed"] == 0


def test_open_bets_are_skipped(dbs, verifier):
    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "BTTS", "Yes", "OPEN", "16881963", "sofascore")
    _add_result(fx_db, "sofascore", "16881963", 1, 1)
    assert verifier.verify_settlements(bet_db, fx_db)["checked"] == 0


def test_unknown_market_is_not_counted_as_a_disagreement(dbs, verifier):
    """_grade_bet returns 'V' for markets it cannot grade — that is 'unknown',
    not 'the recorded grade was wrong'."""
    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "Goalscorer", "Someone", "W", "16881963", "sofascore")
    _add_result(fx_db, "sofascore", "16881963", 1, 1)
    summary = verifier.verify_settlements(bet_db, fx_db)
    assert summary["disagreed"] == 0
    assert summary["ungradeable"] == 1


def test_namespace_is_respected_not_just_the_bare_id(dbs, verifier):
    """A same id in a DIFFERENT namespace must not be used to verify."""
    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore")
    _add_result(fx_db, "betarabia", "16881963", 1, 0)  # different namespace
    summary = verifier.verify_settlements(bet_db, fx_db)
    assert summary["checked"] == 0, "must not cross namespaces to verify"


def test_is_idempotent(dbs, verifier):
    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore")
    _add_result(fx_db, "sofascore", "16881963", 1, 0)
    verifier.verify_settlements(bet_db, fx_db)
    verifier.verify_settlements(bet_db, fx_db)
    assert len(verifier.load_disagreements(bet_db)) == 1, "must upsert, not duplicate"


def test_uses_the_canonical_grader(dbs, verifier, monkeypatch):
    """It must call tools.score_lookup._grade_bet, never re-implement grading.

    If it re-implemented the rules, a disagreement could be this module's bug
    rather than a real mis-grade, which would make the whole measurement
    worthless.
    """
    import tools.score_lookup as sl

    calls = []
    real = sl._grade_bet

    def spy(market, side, hs, aws):
        calls.append((market, side, hs, aws))
        return real(market, side, hs, aws)

    monkeypatch.setattr(sl, "_grade_bet", spy)

    bet_db, fx_db = dbs
    _add_bet(bet_db, "b1", "BTTS", "Yes", "W", "16881963", "sofascore")
    _add_result(fx_db, "sofascore", "16881963", 1, 1)
    verifier.verify_settlements(bet_db, fx_db)

    assert calls == [("BTTS", "Yes", 1, 1)]
