"""edge_milestone_check.py must watch every strategy that actually places bets.

The tool is the project's "can I place real bets yet?" gate, but its tracked
list was hand-maintained and had drifted out of date. MODEL_VALUE_ALIGN — the
only strategy in the whole verified record with a clustered t above the 2.0 bar
(t=+3.52, n=190, +43.5% ROI) — was not in it, so every run reported
MILESTONE_NOT_MET while the best signal went unmeasured. PINNACLE_VALUE
(+$134.98) was missing too.

These tests pin the coverage so a new bet_source cannot silently go unwatched.
"""

import importlib
import sqlite3

import pytest

emc = importlib.import_module("tools.edge_milestone_check")

# Every bet_source the engine has actually written to bet_log and that carries
# real volume. Adding a strategy to the daemon means adding it here too.
EXPECTED = {
    "TIPSTER_FOREBET",
    "TIPSTER_APIFB",
    "TIPSTER_CONSENSUS",
    "STEAM",
    "STEAM_LL",
    "PINNACLE_STEAM",
    "SHARP_STEAM",
    "AI",
    "MODEL_VALUE_ALIGN",
    "PINNACLE_VALUE",
    "STAIR_AI",
    "VALUE_ONLY",
}


def _tracked_patterns():
    return {like for _name, like, _n in emc.TRACKED}


def test_tracked_list_is_exposed_for_inspection():
    """The list must be a module constant, not buried in main()."""
    assert hasattr(emc, "TRACKED"), "TRACKED must be importable"
    assert len(emc.TRACKED) >= len(EXPECTED)


@pytest.mark.parametrize("source", sorted(EXPECTED))
def test_every_live_strategy_is_tracked(source):
    assert source in _tracked_patterns(), f"{source} places bets but is unwatched"


def test_model_value_align_is_tracked():
    """Regression guard for the specific blind spot that hid the best signal."""
    assert "MODEL_VALUE_ALIGN" in _tracked_patterns()


def test_pinnacle_value_is_tracked():
    assert "PINNACLE_VALUE" in _tracked_patterns()


def test_aggregate_row_still_present():
    assert "%" in _tracked_patterns(), "the ALL aggregate row must survive"


def test_tracked_entries_are_well_formed():
    for entry in emc.TRACKED:
        assert len(entry) == 3, entry
        name, like, n_min = entry
        assert isinstance(name, str) and name
        assert isinstance(like, str) and like
        assert isinstance(n_min, int) and n_min > 0


def test_no_duplicate_patterns():
    pats = [like for _n, like, _m in emc.TRACKED]
    assert len(pats) == len(set(pats)), "a duplicated pattern double-counts a strategy"


# ---------------------------------------------------------------------------
# stats correctness against a known fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "bet_log.db")
    con = sqlite3.connect(p)
    con.execute(
        "CREATE TABLE bet_log (pnl REAL, stake REAL, fixture_id TEXT, "
        "result TEXT, result_verified INT, bet_source TEXT, settle_checked_at TEXT)"
    )
    rows = [
        # MODEL_VALUE_ALIGN: 3 wins 1 loss, net +30 on 40 staked
        (20.0, 10.0, "f1", "W", 1, "MODEL_VALUE_ALIGN", "2026-08-24T00:00:00+00:00"),
        (20.0, 10.0, "f2", "W", 1, "MODEL_VALUE_ALIGN", "2026-08-24T00:00:00+00:00"),
        (-10.0, 10.0, "f3", "L", 1, "MODEL_VALUE_ALIGN", "2026-08-24T00:00:00+00:00"),
        (0.0, 10.0, "f4", "W", 1, "MODEL_VALUE_ALIGN", "2026-08-24T00:00:00+00:00"),
        # unverified row must be ignored entirely
        (999.0, 1.0, "f5", "W", 0, "MODEL_VALUE_ALIGN", "2026-08-24T00:00:00+00:00"),
        # a different strategy must not leak in
        (50.0, 10.0, "f6", "W", 1, "PINNACLE_VALUE", "2026-08-24T00:00:00+00:00"),
    ]
    con.executemany("INSERT INTO bet_log VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return p


def test_stats_isolate_the_named_strategy(db):
    con = sqlite3.connect(db)
    s = emc.strategy_stats(con.cursor(), "MODEL_VALUE_ALIGN")
    con.close()
    assert s["n"] == 4, "unverified rows must be excluded"
    assert round(s["net"], 2) == 30.0
    assert round(s["roi"], 1) == 75.0


def test_stats_exclude_unverified_grades(db):
    """The 2026-07-12 audit found ~29% of legacy unverified grades were wrong."""
    con = sqlite3.connect(db)
    s = emc.strategy_stats(con.cursor(), "MODEL_VALUE_ALIGN")
    con.close()
    assert s["net"] < 999, "an unverified +999 row leaked into the stats"
