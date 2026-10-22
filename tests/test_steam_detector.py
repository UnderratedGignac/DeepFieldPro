"""STEAM detector tests: _steam_moves() and _devig_map() in the daemon.

Builds a tmp odds_history sqlite DB (DATA_DIR monkeypatched) and checks the
de-vig + move computation, the monotonicity weighting, and the "no signal
until >=2 snapshots" contract. No network, no real DB.
"""

import sqlite3

import pytest

from tests._daemon_test_utils import import_daemon

lpd = import_daemon()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _devig(odds_by_sel):
    """Independent reference de-vig implementation for expected values."""
    inv = {s: 1.0 / o for s, o in odds_by_sel.items() if o and o > 0}
    tot = sum(inv.values())
    return {s: v / tot for s, v in inv.items()}


@pytest.fixture
def odds_db(tmp_path, monkeypatch):
    """tmp DATA_DIR with deepfield_browser_data/completed_fixtures.db; returns
    an `insert(fid, market, selection, odds, ts)` function."""
    data = tmp_path / "data"
    sub = data / "deepfield_browser_data"
    sub.mkdir(parents=True)
    db = sub / "completed_fixtures.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE odds_history (
               fixture_id TEXT, market TEXT, selection TEXT,
               odds REAL, timestamp TEXT)"""
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(data))

    def insert(fid, market, selection, odds, ts):
        c = sqlite3.connect(db)
        c.execute(
            "INSERT INTO odds_history VALUES (?,?,?,?,?)",
            (str(fid), market, selection, odds, ts),
        )
        c.commit()
        c.close()

    def snapshot(fid, market, odds_by_sel, ts):
        for sel, o in odds_by_sel.items():
            insert(fid, market, sel, o, ts)

    return snapshot


T1, T2, T3 = "2026-07-10 08:00:00", "2026-07-10 09:00:00", "2026-07-10 10:00:00"


# ---------------------------------------------------------------------------
# _devig_map
# ---------------------------------------------------------------------------

class TestDevigMap:
    def test_two_way_devig_sums_to_one(self):
        dv = lpd._devig_map({"Home": 1.8, "Away": 2.25})
        assert sum(dv.values()) == pytest.approx(1.0)
        assert dv["Home"] == pytest.approx((1 / 1.8) / (1 / 1.8 + 1 / 2.25))

    def test_three_way_devig_sums_to_one_and_removes_vig(self):
        odds = {"Home": 2.10, "Draw": 3.30, "Away": 3.60}
        dv = lpd._devig_map(odds)
        assert sum(dv.values()) == pytest.approx(1.0)
        # raw implied probs sum > 1 (the vig); devigged are proportionally lower
        raw = {s: 1 / o for s, o in odds.items()}
        assert sum(raw.values()) > 1.0
        for s in odds:
            assert dv[s] < raw[s]

    def test_single_selection_returns_none(self):
        assert lpd._devig_map({"Home": 2.0}) is None

    def test_zero_and_none_odds_filtered(self):
        # only one valid price left -> not devig-able
        assert lpd._devig_map({"Home": 2.0, "Away": 0}) is None
        assert lpd._devig_map({"Home": 2.0, "Away": None}) is None


# ---------------------------------------------------------------------------
# _steam_moves
# ---------------------------------------------------------------------------

class TestSteamMoves:
    def test_empty_history_returns_empty(self, odds_db):
        assert lpd._steam_moves("f1", "1X2") == {}

    def test_missing_db_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lpd, "DATA_DIR", str(tmp_path / "nowhere"))
        assert lpd._steam_moves("f1", "1X2") == {}

    def test_single_snapshot_returns_empty(self, odds_db):
        odds_db("f1", "1X2", {"Home": 2.0, "Away": 2.0}, T1)
        assert lpd._steam_moves("f1", "1X2") == {}

    def test_two_snapshots_devig_move(self, odds_db):
        odds_db("f1", "1X2", {"Home": 2.0, "Away": 2.0}, T1)
        odds_db("f1", "1X2", {"Home": 1.8, "Away": 2.25}, T2)
        moves = lpd._steam_moves("f1", "1X2")

        early = _devig({"Home": 2.0, "Away": 2.0})
        late = _devig({"Home": 1.8, "Away": 2.25})
        exp_home = late["Home"] - early["Home"]  # ~ +0.0556
        exp_away = late["Away"] - early["Away"]

        # single step -> monotonicity 1.0 -> effective == raw
        assert moves["Home"] == pytest.approx(exp_home)
        assert moves["Away"] == pytest.approx(exp_away)
        assert exp_home > 0 > exp_away

        meta = moves["__meta__"]
        assert meta["Home"]["monotonicity"] == 1.0
        assert meta["Home"]["raw"] == pytest.approx(exp_home)
        assert meta["Home"]["n_snaps"] == 2

    def test_moves_sum_to_zero_across_selections(self, odds_db):
        odds_db("f1", "1X2", {"Home": 2.10, "Draw": 3.30, "Away": 3.60}, T1)
        odds_db("f1", "1X2", {"Home": 1.90, "Draw": 3.40, "Away": 4.20}, T2)
        moves = lpd._steam_moves("f1", "1X2")
        raw_sum = sum(v["raw"] for v in moves["__meta__"].values())
        assert raw_sum == pytest.approx(0.0, abs=1e-9)

    def test_spike_and_reverse_is_downweighted(self, odds_db):
        """A spike-then-reverse pattern must score lower than its raw move
        (fake-steam filter): effective = raw * monotonicity."""
        odds_db("f1", "1X2", {"Home": 2.00, "Away": 2.00}, T1)
        odds_db("f1", "1X2", {"Home": 1.60, "Away": 2.67}, T2)  # big spike toward Home
        odds_db("f1", "1X2", {"Home": 1.95, "Away": 2.05}, T3)  # mostly reversed
        moves = lpd._steam_moves("f1", "1X2")

        early = _devig({"Home": 2.00, "Away": 2.00})
        late = _devig({"Home": 1.95, "Away": 2.05})
        raw = late["Home"] - early["Home"]
        # steps: up then down -> 1 of 2 aligned -> monotonicity 0.5
        assert moves["__meta__"]["Home"]["monotonicity"] == 0.5
        assert moves["Home"] == pytest.approx(raw * 0.5)
        assert abs(moves["Home"]) < abs(raw) or raw == 0

    def test_smooth_trend_keeps_full_weight(self, odds_db):
        odds_db("f1", "1X2", {"Home": 2.10, "Away": 1.90}, T1)
        odds_db("f1", "1X2", {"Home": 2.00, "Away": 1.98}, T2)
        odds_db("f1", "1X2", {"Home": 1.92, "Away": 2.06}, T3)
        moves = lpd._steam_moves("f1", "1X2")
        assert moves["__meta__"]["Home"]["monotonicity"] == 1.0
        early = _devig({"Home": 2.10, "Away": 1.90})
        late = _devig({"Home": 1.92, "Away": 2.06})
        assert moves["Home"] == pytest.approx(late["Home"] - early["Home"])

    def test_incomplete_snapshots_are_ignored(self, odds_db):
        """A timestamp with <2 selections can't be de-vigged; with only one
        complete snapshot remaining the detector must return {}."""
        odds_db("f1", "1X2", {"Home": 2.0, "Away": 2.0}, T1)
        odds_db("f1", "1X2", {"Home": 1.8}, T2)  # partial snapshot
        assert lpd._steam_moves("f1", "1X2") == {}

    def test_market_and_fixture_are_isolated(self, odds_db):
        odds_db("f1", "1X2", {"Home": 2.0, "Away": 2.0}, T1)
        odds_db("f1", "1X2", {"Home": 1.8, "Away": 2.25}, T2)
        odds_db("f2", "1X2", {"Home": 3.0, "Away": 1.4}, T1)
        odds_db("f1", "Over/Under 2.5", {"Over": 1.9, "Under": 1.9}, T1)
        moves = lpd._steam_moves("f2", "1X2")
        assert moves == {}  # f2 has one snapshot only
        moves_f1_ou = lpd._steam_moves("f1", "Over/Under 2.5")
        assert moves_f1_ou == {}  # OU market has one snapshot only
