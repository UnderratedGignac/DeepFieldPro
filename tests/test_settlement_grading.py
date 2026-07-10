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
    clv         REAL
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
