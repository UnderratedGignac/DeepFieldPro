"""Settlement tests: settle_open_bets() grading 1X2 (and O/U pushes) from real scores.

Runs the REAL settle_open_bets() against a tmp DATA_DIR sqlite bet_log.db.
Every external feed is stubbed:
  - get_todays_fixtures            -> []
  - src.free_results_scraper       -> our injected finished-results dict
  - src.flashscore_scraper / src.sofascore_results_scraper -> {}
  - fetch_api_football_results     -> {}
  - tools.pinnacle_value / tools.score_lookup -> inert stubs
  - deep score lookup              -> skipped via _deep_lookup_last_run throttle
  - bankroll routing               -> recorded, not executed

No network, no real DB is touched.
"""

import datetime
import json
import sqlite3
import sys
import time
import types

import pytest

from tests._daemon_test_utils import import_daemon

lpd = import_daemon()


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

BET_LOG_SCHEMA = """
CREATE TABLE bet_log (
    bet_id      TEXT PRIMARY KEY,
    match_id    TEXT,
    player_id   TEXT,
    market_type TEXT,
    entry_odds  REAL,
    fair_odds   REAL,
    edge_pct    REAL,
    stake       REAL,
    result      TEXT DEFAULT 'OPEN',
    pnl         REAL DEFAULT 0,
    placed_at   TEXT,
    bet_source  TEXT,
    is_recommended INTEGER DEFAULT 1,
    line        TEXT,
    side        TEXT,
    fixture_id  TEXT,
    league      TEXT,
    closing_odds REAL,
    clv         REAL,
    pinnacle_clv REAL
)
"""


def _old_iso(hours=48):
    return (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    ).isoformat()


def _mk_bet(
    bet_id,
    match,
    selection,
    market="1X2",
    odds=2.5,
    stake=10.0,
    source="AI",
    placed_at=None,
):
    return (
        bet_id,
        match,
        f"{match} ({selection})",
        market,
        odds,
        stake,
        source,
        None,  # fixture_id
        selection,  # side
        placed_at or _old_iso(),
    )


def _make_data_dir(tmp_path, bets=(), parlays=()):
    data = tmp_path / "data"
    data.mkdir()
    conn = sqlite3.connect(data / "bet_log.db")
    conn.execute(BET_LOG_SCHEMA)
    conn.execute(
        """CREATE TABLE parlay_log (
               parlay_id TEXT PRIMARY KEY, legs_json TEXT, stake REAL,
               total_odds REAL, result TEXT DEFAULT 'OPEN', pnl REAL DEFAULT 0,
               placed_at TEXT)"""
    )
    conn.execute("CREATE TABLE predictions (fixture_id TEXT, kickoff TEXT)")
    for b in bets:
        conn.execute(
            "INSERT INTO bet_log (bet_id, match_id, player_id, market_type,"
            " entry_odds, stake, bet_source, fixture_id, side, placed_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            b,
        )
    for p in parlays:
        conn.execute(
            "INSERT INTO parlay_log (parlay_id, legs_json, stake, total_odds,"
            " placed_at) VALUES (?,?,?,?,?)",
            p,
        )
    conn.commit()
    conn.close()
    # Install the provenance columns + enforcement trigger so these E2E tests
    # exercise the real "no unverified W/L" guarantee.
    from src.settlement_provenance import ensure_settlement_provenance

    ensure_settlement_provenance(str(data / "bet_log.db"))
    return data


def _stub_module(monkeypatch, name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, name, mod)


def _run_settlement(monkeypatch, data_dir, finished):
    """Run the real settle_open_bets() fully sandboxed. Returns the list of
    (payout, pnl, bet_source) tuples routed to the bankroll ledger."""
    routed = []
    settled_direct = []  # parlay path calls bankroll_tracker.register_settlement

    monkeypatch.setattr(lpd, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(lpd, "get_todays_fixtures", lambda: [])
    monkeypatch.setattr(lpd, "fetch_api_football_results", lambda: {})
    monkeypatch.setattr(lpd, "load_predictions_from_db", lambda: {})
    monkeypatch.setattr(lpd, "_kickoff_map", lambda: {})
    monkeypatch.setattr(lpd, "_CLV_TRACKER_OK", False)
    monkeypatch.setattr(lpd, "_deep_lookup_last_run", time.time())
    monkeypatch.setattr(
        lpd,
        "_register_settlement_routed",
        lambda payout, pnl, bet_source: routed.append((payout, pnl, bet_source)),
    )

    _stub_module(
        monkeypatch,
        "src.free_results_scraper",
        get_finished_results=lambda dates=None: dict(finished),
    )
    _stub_module(
        monkeypatch,
        "src.flashscore_scraper",
        get_finished_results=lambda dates=None: {},
    )
    _stub_module(
        monkeypatch,
        "src.sofascore_results_scraper",
        get_finished_results=lambda dates=None: {},
    )
    _stub_module(
        monkeypatch,
        "tools.pinnacle_value",
        clv_from_pinnacle=lambda *a, **k: None,
        clv_from_pinnacle_ou25=lambda *a, **k: None,
    )
    _stub_module(
        monkeypatch,
        "tools.score_lookup",
        _name_similarity=lambda a, b: 0.0,
    )
    # Parlay settlement imports register_settlement directly.
    import src.bankroll_tracker as bt

    monkeypatch.setattr(
        bt,
        "register_settlement",
        lambda payout, pnl, db_path=None: settled_direct.append((payout, pnl)),
    )

    lpd.settle_open_bets()
    return routed, settled_direct


def _bet_rows(data_dir):
    conn = sqlite3.connect(data_dir / "bet_log.db")
    rows = {
        r[0]: {"result": r[1], "pnl": r[2]}
        for r in conn.execute("SELECT bet_id, result, pnl FROM bet_log")
    }
    conn.close()
    return rows


def _prov(data_dir, bet_id):
    conn = sqlite3.connect(data_dir / "bet_log.db")
    r = conn.execute(
        "SELECT result, settle_source, result_verified, settle_reason FROM bet_log WHERE bet_id=?",
        (bet_id,),
    ).fetchone()
    conn.close()
    return {"result": r[0], "settle_source": r[1], "result_verified": r[2], "settle_reason": r[3]}


# ---------------------------------------------------------------------------
# 1X2 grading
# ---------------------------------------------------------------------------

class Test1X2Grading:
    def test_home_win_graded_w_with_correct_pnl(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home", odds=2.5, stake=10.0)],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Alpha FC vs Beta United": (2, 0)}
        )
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "W"
        assert rows["b1"]["pnl"] == pytest.approx(15.0)  # 10 * (2.5 - 1)
        assert routed == [(pytest.approx(25.0), pytest.approx(15.0), "AI")]

    def test_home_pick_graded_l_when_away_wins(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home", odds=3.0, stake=20.0)],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Alpha FC vs Beta United": (0, 1)}
        )
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "L"
        assert rows["b1"]["pnl"] == pytest.approx(-20.0)
        assert routed == [(pytest.approx(0.0), pytest.approx(-20.0), "AI")]

    def test_draw_pick_wins_on_drawn_score(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Gamma Town vs Delta City", "Draw", odds=3.2, stake=5.0)],
        )
        _run_settlement(monkeypatch, data, {"Gamma Town vs Delta City": (1, 1)})
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "W"
        assert rows["b1"]["pnl"] == pytest.approx(5.0 * 2.2)

    def test_draw_pick_loses_on_decisive_score(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Gamma Town vs Delta City", "Draw", odds=3.2, stake=5.0)],
        )
        _run_settlement(monkeypatch, data, {"Gamma Town vs Delta City": (2, 1)})
        assert _bet_rows(data)["b1"]["result"] == "L"

    def test_away_win_graded_from_reversed_feed_orientation(self, tmp_path, monkeypatch):
        """The result feed sometimes lists teams swapped; scores must be swapped
        back to the bet's perspective before grading."""
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Botev Vratsa vs Levski Sofia", "Away", odds=2.0, stake=10.0)],
        )
        # Feed reversed: Levski (home in feed) won 3-0 == away team of the bet won.
        _run_settlement(
            monkeypatch, data, {"Levski Sofia vs Botev Vratsa": (3, 0)}
        )
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "W"
        assert rows["b1"]["pnl"] == pytest.approx(10.0)

    def test_unmatched_bet_stays_open(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Obscure XI vs Unknown SK", "Home")],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Some Other vs Match Here": (1, 0)}
        )
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert routed == []

    def test_u23_bet_not_settled_against_senior_result(self, tmp_path, monkeypatch):
        """End-to-end regression (2026-07-11 forensics): a U23 bet must NOT be
        graded against the senior fixture's score. Only the senior 1-3 result
        is in the feed; the U23 bet stays OPEN rather than settling wrong."""
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Green Gully SC U23 vs Altona Magic SC U23", "Away",
                          odds=2.95, stake=9.65)],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Green Gully vs Altona Magic": (1, 3)}
        )
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert routed == []

    def test_u23_bet_settles_against_matching_u23_result(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Green Gully SC U23 vs Altona Magic SC U23", "Home",
                          odds=2.0, stake=10.0)],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Green Gully U23 vs Altona Magic U23": (2, 0)}
        )
        assert _bet_rows(data)["b1"]["result"] == "W"
        assert routed == [(pytest.approx(20.0), pytest.approx(10.0), "AI")]

    def test_senior_bet_not_settled_against_u23_result(self, tmp_path, monkeypatch):
        """The mirror case: a senior bet must not be graded off a U23 score."""
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Canberra Juventus vs O'Connor Knights", "Home")],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Canberra Juventus U23 vs O'Connor Knights U23": (1, 0)}
        )
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert routed == []


class TestSettlementProvenance:
    """The 'never assume correct' guarantee end-to-end through settle_open_bets."""

    def test_verified_win_records_source_and_flag(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home", odds=2.5, stake=10.0)],
        )
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (2, 0)})
        p = _prov(data, "b1")
        assert p["result"] == "W"
        assert p["result_verified"] == 1
        assert p["settle_source"] in ("name-match", "fid-direct", "score-match")
        assert p["settle_reason"]  # the matched fixture is recorded

    def test_unscrapeable_score_bet_voids_with_reason(self, tmp_path, monkeypatch):
        """A score-market bet whose match is long finished but that no feed can
        map must VOID with the reason recorded — not stay OPEN, not guess."""
        # Give it a kickoff 100h ago via the predictions table so the time-based
        # void pass fires (its window default is 48h for score markets).
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Obscure XI vs Unknown SK", "Home",
                          placed_at=_old_iso(hours=100))],
        )
        conn = sqlite3.connect(data / "bet_log.db")
        conn.execute("UPDATE bet_log SET fixture_id='99001' WHERE bet_id='b1'")
        conn.execute(
            "INSERT INTO predictions (fixture_id, kickoff) VALUES ('99001', ?)",
            (_old_iso(hours=100),),
        )
        conn.commit()
        conn.close()
        # No matching result in the feed -> unscrapeable.
        _run_settlement(monkeypatch, data, {"Totally Different vs Teams Here": (1, 1)})
        p = _prov(data, "b1")
        assert p["result"] == "VOID"
        assert p["settle_reason"] and "past kickoff" in p["settle_reason"]

    def test_recent_bet_not_settled_even_with_result(self, tmp_path, monkeypatch):
        """Finished-by-now guard: a bet placed 1h ago with unknown kickoff cannot
        have finished — must stay OPEN even if a fuzzy 'result' exists (the
        in-play false-WIN bug class)."""
        data = _make_data_dir(
            tmp_path,
            bets=[
                _mk_bet(
                    "b1",
                    "Alpha FC vs Beta United",
                    "Home",
                    placed_at=_old_iso(hours=1),
                )
            ],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Alpha FC vs Beta United": (2, 0)}
        )
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert routed == []

    def test_multiple_bets_graded_independently(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[
                _mk_bet("w", "Alpha FC vs Beta United", "Home", odds=2.0, stake=10.0),
                _mk_bet("l", "Alpha FC vs Beta United", "Away", odds=4.0, stake=10.0),
            ],
        )
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (1, 0)})
        rows = _bet_rows(data)
        assert rows["w"]["result"] == "W"
        assert rows["l"]["result"] == "L"


# ---------------------------------------------------------------------------
# Over/Under grading incl. push -> VOID
# ---------------------------------------------------------------------------

class TestOverUnderGrading:
    def test_over_25_win(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[
                _mk_bet(
                    "b1", "Alpha FC vs Beta United", "Over 2.5",
                    market="Over/Under 2.5", odds=1.9, stake=10.0,
                )
            ],
        )
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (2, 1)})
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "W"
        assert rows["b1"]["pnl"] == pytest.approx(9.0)

    def test_under_25_loss(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[
                _mk_bet(
                    "b1", "Alpha FC vs Beta United", "Under 2.5",
                    market="Over/Under 2.5", odds=1.9, stake=10.0,
                )
            ],
        )
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (2, 1)})
        assert _bet_rows(data)["b1"]["result"] == "L"

    def test_integer_line_push_voids_and_refunds_stake(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[
                _mk_bet(
                    "b1", "Alpha FC vs Beta United", "Over 2",
                    market="Over/Under 2.0", odds=1.9, stake=10.0,
                )
            ],
        )
        routed, _ = _run_settlement(
            monkeypatch, data, {"Alpha FC vs Beta United": (1, 1)}
        )
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "VOID"
        assert rows["b1"]["pnl"] == pytest.approx(0.0)
        # VOID refunds the stake: payout == stake, pnl == 0
        assert routed == [(pytest.approx(10.0), pytest.approx(0.0), "AI")]


# ---------------------------------------------------------------------------
# Parlay settlement
# ---------------------------------------------------------------------------

class TestParlaySettlement:
    """NOTE (real current behavior): settle_open_bets() returns early when
    there are NO open single bets ('if not open_bets: return'), so parlays only
    settle while at least one single bet is open. Each test therefore seeds a
    companion open single bet to reach the parlay path."""

    COMPANION = _mk_bet("companion", "Alpha FC vs Beta United", "Home")

    def _legs(self, *sels):
        return json.dumps(
            [
                {"match": m, "market": "Match Result", "selection": s}
                for m, s in sels
            ]
        )

    def test_parlay_all_legs_win(self, tmp_path, monkeypatch):
        legs = self._legs(
            ("Alpha FC vs Beta United", "1"), ("Gamma Town vs Delta City", "2")
        )
        data = _make_data_dir(
            tmp_path,
            bets=[self.COMPANION],
            parlays=[("p1", legs, 10.0, 6.0, _old_iso())],
        )
        _, direct = _run_settlement(
            monkeypatch,
            data,
            {
                "Alpha FC vs Beta United": (2, 0),
                "Gamma Town vs Delta City": (0, 1),
            },
        )
        conn = sqlite3.connect(data / "bet_log.db")
        result, pnl = conn.execute(
            "SELECT result, pnl FROM parlay_log WHERE parlay_id='p1'"
        ).fetchone()
        conn.close()
        assert result == "W"
        assert pnl == pytest.approx(50.0)  # 10 * (6 - 1)
        assert direct == [(pytest.approx(60.0), pytest.approx(50.0))]

    def test_parlay_one_leg_lost_loses_whole_parlay(self, tmp_path, monkeypatch):
        legs = self._legs(
            ("Alpha FC vs Beta United", "1"), ("Gamma Town vs Delta City", "2")
        )
        data = _make_data_dir(
            tmp_path,
            bets=[self.COMPANION],
            parlays=[("p1", legs, 10.0, 6.0, _old_iso())],
        )
        _, direct = _run_settlement(
            monkeypatch,
            data,
            {
                "Alpha FC vs Beta United": (0, 2),  # leg 1 loses
                "Gamma Town vs Delta City": (0, 1),
            },
        )
        conn = sqlite3.connect(data / "bet_log.db")
        result, pnl = conn.execute(
            "SELECT result, pnl FROM parlay_log WHERE parlay_id='p1'"
        ).fetchone()
        conn.close()
        assert result == "L"
        assert pnl == pytest.approx(-10.0)
        assert direct == [(pytest.approx(0.0), pytest.approx(-10.0))]

    def test_parlay_with_unresolved_leg_stays_open(self, tmp_path, monkeypatch):
        legs = self._legs(
            ("Alpha FC vs Beta United", "1"), ("No Result vs For This", "1")
        )
        data = _make_data_dir(
            tmp_path,
            bets=[self.COMPANION],
            parlays=[("p1", legs, 10.0, 6.0, _old_iso())],
        )
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (2, 0)})
        conn = sqlite3.connect(data / "bet_log.db")
        (result,) = conn.execute(
            "SELECT result FROM parlay_log WHERE parlay_id='p1'"
        ).fetchone()
        conn.close()
        assert result == "OPEN"


# ---------------------------------------------------------------------------
# Deep-lookup trust gate (2026-07-12): google-sourced and implausible scores
# must never grade a bet — they are the proven garbage class (15-2 h2h records,
# 0-12 stat boxes parsed as scores, wrong-match team-page rows).
# ---------------------------------------------------------------------------

class TestDeepLookupTrustGate:
    def _run_deep(self, tmp_path, monkeypatch, lookup_result):
        data = _make_data_dir(
            tmp_path, bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home", odds=2.0, stake=10.0)]
        )
        routed = []
        monkeypatch.setattr(lpd, "DATA_DIR", str(data))
        monkeypatch.setattr(lpd, "get_todays_fixtures", lambda: [])
        monkeypatch.setattr(lpd, "fetch_api_football_results", lambda: {})
        monkeypatch.setattr(lpd, "load_predictions_from_db", lambda: {})
        monkeypatch.setattr(lpd, "_kickoff_map", lambda: {})
        monkeypatch.setattr(lpd, "_CLV_TRACKER_OK", False)
        monkeypatch.setattr(lpd, "_deep_lookup_last_run", 0.0)  # deep pass ENABLED
        monkeypatch.setattr(
            lpd, "_register_settlement_routed", lambda p, n, s: routed.append((p, n, s))
        )
        _stub_module(
            monkeypatch, "src.free_results_scraper",
            get_finished_results=lambda dates=None: {"Unrelated vs Other Match": (1, 0)},
        )
        _stub_module(monkeypatch, "src.flashscore_scraper", get_finished_results=lambda dates=None: {})
        _stub_module(monkeypatch, "src.sofascore_results_scraper", get_finished_results=lambda dates=None: {})
        _stub_module(
            monkeypatch, "tools.pinnacle_value",
            clv_from_pinnacle=lambda *a, **k: None, clv_from_pinnacle_ou25=lambda *a, **k: None,
        )

        def _grade(mkt, side, hs, as_):
            if mkt != "1X2":
                return "VOID"
            s = side.lower()
            if "home" in s:
                return "W" if hs > as_ else "L"
            if "away" in s:
                return "W" if as_ > hs else "L"
            return "W" if hs == as_ else "L"

        _stub_module(
            monkeypatch, "tools.score_lookup",
            _name_similarity=lambda a, b: 0.0,
            lookup_score=lambda h, a, use_browser=True: lookup_result,
            _grade_bet=_grade,
            _parse_match_teams=lambda mid: tuple(t.strip() for t in mid.split(" vs ", 1))
            if mid and " vs " in mid else None,
        )
        import src.bankroll_tracker as bt
        monkeypatch.setattr(bt, "register_settlement", lambda p, n, db_path=None: None)
        lpd.settle_open_bets()
        return data, routed

    def test_implausible_score_never_grades(self, tmp_path, monkeypatch):
        # 15-2 is a scraped h2h record, not a football score.
        data, routed = self._run_deep(tmp_path, monkeypatch, (15, 2, "flashscore-home"))
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert routed == []
        assert "b1" in {r["bet_id"] for r in _review_rows(data)}

    def test_google_source_never_grades_even_when_plausible(self, tmp_path, monkeypatch):
        # google's score box shows h2h/live/stat numbers indistinguishable from
        # finals — proven wrong even at plausible scorelines (0-0, 2-0 cases).
        data, routed = self._run_deep(tmp_path, monkeypatch, (2, 0, "google"))
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert routed == []

    def test_plausible_flashscore_score_still_settles(self, tmp_path, monkeypatch):
        data, routed = self._run_deep(tmp_path, monkeypatch, (2, 1, "flashscore-home"))
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "W"
        assert rows["b1"]["pnl"] == pytest.approx(10.0)
        p = _prov(data, "b1")
        assert p["settle_source"] == "deep-lookup"
        assert p["result_verified"] == 1


# ---------------------------------------------------------------------------
# No finished results at all -> nothing happens
# ---------------------------------------------------------------------------

def test_no_results_leaves_everything_open(tmp_path, monkeypatch):
    data = _make_data_dir(
        tmp_path, bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home")]
    )
    routed, direct = _run_settlement(monkeypatch, data, {})
    assert _bet_rows(data)["b1"]["result"] == "OPEN"
    assert routed == []
    assert direct == []


# ---------------------------------------------------------------------------
# Manual-review queue: refuse-to-grade when no covered source has the fixture
# ---------------------------------------------------------------------------

def _review_rows(data_dir, include_resolved=False):
    from src.settlement_review import list_review_queue

    return list_review_queue(str(data_dir / "bet_log.db"), include_resolved=include_resolved)


class TestManualReviewQueue:
    """The Uruguay-Tercera-Reserves / Australian-NPL coverage-gap class: a bet whose
    match no covered results source carries must be left OPEN and flagged for manual
    review — never graded off a fuzzy collision, never silently rotting OPEN."""

    def test_finished_unmappable_bet_is_queued_for_review(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path, bets=[_mk_bet("b1", "Obscure XI vs Unknown SK", "Home")]
        )
        # finished feed is non-empty but has nothing matching this fixture.
        _run_settlement(monkeypatch, data, {"Some Other vs Match Here": (1, 0)})
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        q = _review_rows(data)
        assert [r["bet_id"] for r in q] == ["b1"]
        assert q[0]["reason"]  # a human-readable reason is recorded
        assert q[0]["match_id"] == "Obscure XI vs Unknown SK"

    def test_ambiguous_match_is_queued_not_graded(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path, bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home")]
        )
        # Two equally-good name matches that DISAGREE on the score -> ambiguous.
        _run_settlement(
            monkeypatch,
            data,
            {"Alpha FC vs Beta United": (2, 0), "Alpha vs Beta": (0, 1)},
        )
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert [r["bet_id"] for r in _review_rows(data)] == ["b1"]

    def test_agreeing_scores_of_mixed_types_are_not_ambiguous(self, tmp_path, monkeypatch):
        """Regression (2026-07-12 E2E run 2): two sources listed the same match
        under slightly different names with the SAME score, but one source
        returns list scores and another tuples — and (3,2) != [3,2] in Python,
        so the ambiguity guard falsely skipped a settleable bet. Scores that
        agree numerically must settle regardless of container type."""
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Galway United vs Sligo Rovers", "Home", odds=2.0, stake=10.0)],
        )
        routed = []
        monkeypatch.setattr(lpd, "DATA_DIR", str(data))
        monkeypatch.setattr(lpd, "get_todays_fixtures", lambda: [])
        monkeypatch.setattr(lpd, "fetch_api_football_results", lambda: {})
        monkeypatch.setattr(lpd, "load_predictions_from_db", lambda: {})
        monkeypatch.setattr(lpd, "_kickoff_map", lambda: {})
        monkeypatch.setattr(lpd, "_CLV_TRACKER_OK", False)
        monkeypatch.setattr(lpd, "_deep_lookup_last_run", time.time())
        monkeypatch.setattr(
            lpd, "_register_settlement_routed", lambda p, n, s: routed.append((p, n, s))
        )
        _stub_module(
            monkeypatch, "src.free_results_scraper",
            get_finished_results=lambda dates=None: {"Galway United vs Sligo Rovers": (3, 2)},
        )
        _stub_module(
            monkeypatch, "src.flashscore_scraper",
            get_finished_results=lambda dates=None: {"Galway vs Sligo Rovers": [3, 2]},  # list!
        )
        _stub_module(monkeypatch, "src.sofascore_results_scraper", get_finished_results=lambda dates=None: {})
        _stub_module(
            monkeypatch, "tools.pinnacle_value",
            clv_from_pinnacle=lambda *a, **k: None, clv_from_pinnacle_ou25=lambda *a, **k: None,
        )
        _stub_module(monkeypatch, "tools.score_lookup", _name_similarity=lambda a, b: 0.0)
        import src.bankroll_tracker as bt
        monkeypatch.setattr(bt, "register_settlement", lambda p, n, db_path=None: None)
        lpd.settle_open_bets()
        rows = _bet_rows(data)
        assert rows["b1"]["result"] == "W"
        assert rows["b1"]["pnl"] == pytest.approx(10.0)

    def test_graded_bet_is_never_queued(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home", odds=2.0, stake=10.0)],
        )
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (2, 0)})
        assert _bet_rows(data)["b1"]["result"] == "W"
        assert _review_rows(data, include_resolved=True) == []

    def test_unmappable_bet_queued_even_after_a_settle_in_same_sweep(self, tmp_path, monkeypatch):
        """Regression (2026-07-12 E2E): queueing used a SECOND sqlite connection
        while the settlement connection held the write lock from an earlier
        UPDATE in the same sweep -> 'database is locked' -> silently swallowed
        -> the unmappable bet never reached the review queue. The settleable bet
        MUST come first in the sweep to reproduce."""
        data = _make_data_dir(
            tmp_path,
            bets=[
                _mk_bet("b_settles", "Alpha FC vs Beta United", "Home", odds=2.0, stake=10.0),
                _mk_bet("b_unmap", "Obscure XI vs Unknown SK", "Home"),
            ],
        )
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (2, 0)})
        rows = _bet_rows(data)
        assert rows["b_settles"]["result"] == "W"
        assert rows["b_unmap"]["result"] == "OPEN"
        assert "b_unmap" in {r["bet_id"] for r in _review_rows(data)}

    def test_sim2_fallback_respects_level_guard(self, tmp_path, monkeypatch):
        """Regression (2026-07-12 E2E): the sim2 secondary matcher graded a
        senior bet off a U21 fixture ('Melbourne City NPL' -> 'Melbourne City
        U21 [sim2]'). Cross-level pairs must be rejected in the sim2 pass just
        like in the primary matcher."""
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Green Gully vs Altona Magic", "Home")],
        )
        # Simulate production sim2 behaviour: high similarity for the same club
        # at DIFFERENT squad levels ("Green Gully" vs "Green Gully U23"), zero
        # across clubs — so only the level guard can stop the cross-level grade
        # (a symmetric always-0.9 stub would trip the ambiguity guard instead).
        def _sim(a, b):
            return 0.9 if a.split()[0].lower() == b.split()[0].lower() else 0.0

        _stub_module(monkeypatch, "tools.score_lookup", _name_similarity=_sim)
        routed = []
        monkeypatch.setattr(lpd, "DATA_DIR", str(data))
        monkeypatch.setattr(lpd, "get_todays_fixtures", lambda: [])
        monkeypatch.setattr(lpd, "fetch_api_football_results", lambda: {})
        monkeypatch.setattr(lpd, "load_predictions_from_db", lambda: {})
        monkeypatch.setattr(lpd, "_kickoff_map", lambda: {})
        monkeypatch.setattr(lpd, "_CLV_TRACKER_OK", False)
        monkeypatch.setattr(lpd, "_deep_lookup_last_run", time.time())
        monkeypatch.setattr(
            lpd, "_register_settlement_routed", lambda p, n, s: routed.append((p, n, s))
        )
        _stub_module(
            monkeypatch, "src.free_results_scraper",
            get_finished_results=lambda dates=None: {"Green Gully U23 vs Altona Magic U23": (1, 3)},
        )
        _stub_module(monkeypatch, "src.flashscore_scraper", get_finished_results=lambda dates=None: {})
        _stub_module(monkeypatch, "src.sofascore_results_scraper", get_finished_results=lambda dates=None: {})
        _stub_module(
            monkeypatch, "tools.pinnacle_value",
            clv_from_pinnacle=lambda *a, **k: None, clv_from_pinnacle_ou25=lambda *a, **k: None,
        )
        import src.bankroll_tracker as bt
        monkeypatch.setattr(bt, "register_settlement", lambda p, n, db_path=None: None)
        lpd.settle_open_bets()
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert routed == []

    def test_queued_bet_resolved_once_result_appears(self, tmp_path, monkeypatch):
        data = _make_data_dir(
            tmp_path,
            bets=[_mk_bet("b1", "Alpha FC vs Beta United", "Home", odds=2.0, stake=10.0)],
        )
        # Sweep 1: results exist but none map -> queued + OPEN.
        _run_settlement(monkeypatch, data, {"Zzz vs Yyy": (0, 0)})
        assert _bet_rows(data)["b1"]["result"] == "OPEN"
        assert [r["bet_id"] for r in _review_rows(data)] == ["b1"]
        # Sweep 2: the real result is now published -> graded, queue row resolved.
        _run_settlement(monkeypatch, data, {"Alpha FC vs Beta United": (2, 0)})
        assert _bet_rows(data)["b1"]["result"] == "W"
        assert _review_rows(data) == []  # nothing pending
        allrows = _review_rows(data, include_resolved=True)
        assert len(allrows) == 1 and allrows[0]["resolved"] == 1
