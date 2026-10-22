"""Over/Under prices must come from the line they were quoted on.

Betarabia quotes every total with its line (`additional_value`), coded
ODD_TTL_1_OVR / ODD_TTL_1_UND for full-time goals. The scraper only had a
branch for the OVER code, so every full-time UNDER was stored as a bare
"UNDER" with its line lost. First-half, Asian and team totals were stored as
bare "OVER"/"UNDER" under "Total Goals" too.

The daemon's parser then read any line-less total as 2.5, last row winning, and
also folded 1.5/3.5 lines into 2.5 when no 2.5 row existed. On 2026-10-21 every
one of the day's 10 MODEL_VALUE_ALIGN bets was priced from the wrong line
(e.g. Under 2.5 logged at 2.52 when the real 2.5 Under was 1.60).
"""

import importlib
import re
import sqlite3

import pytest

lpd = importlib.import_module("src.live_predictions_daemon")
kambi = importlib.import_module("src.kambi_scraper")
scraper = importlib.import_module("src.betarabia_scraper")


# ---------------------------------------------------------------------------
# scraper: keep the line on the UNDER side
# ---------------------------------------------------------------------------


def test_full_time_under_keeps_its_line():
    """The raw API shape: team_name 'UNDER', additional_value ' 2.5'."""
    sel = scraper._normalize_selection("UNDER", "ODD_TTL_1_UND", {}, " 2.5")
    assert sel.startswith("Total UNDER")
    assert re.search(r"2\.5", sel), f"line lost: {sel!r}"


def test_full_time_under_maps_to_total_goals():
    assert scraper.ODD_CODE_MAP.get("ODD_TTL_1_UND") == "Total Goals"


@pytest.mark.parametrize(
    "code", ["ODD_HT1_TTL_OVR", "ODD_HT1_TTL_UND", "ODD_TTL_ASN_1_OVR", "ODD_INDTTL1_1_UND"]
)
def test_other_totals_never_look_like_full_time_lines(code):
    """First-half, Asian and team totals must not pass as 'Total OVER/UNDER <line>'."""
    sel = scraper._normalize_selection("OVER", code, {}, " 2.5")
    assert not re.match(r"Total (OVER|UNDER)\s+\d", sel), f"{code} -> {sel!r}"


# ---------------------------------------------------------------------------
# daemon: price O/U 2.5 from the 2.5 line only
# ---------------------------------------------------------------------------


@pytest.fixture
def stream(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    monkeypatch.setattr(kambi, "fetch_kambi_1x2", lambda: {})

    def _write(markets):
        con = sqlite3.connect(str(d / "odds_stream.db"))
        con.execute(
            "CREATE TABLE fixture (fixture_id TEXT PRIMARY KEY, home_team TEXT, "
            "away_team TEXT, kickoff_time TEXT, kickoff_date TEXT, league_id TEXT, "
            "tournament_name TEXT, scraped_at TEXT)"
        )
        con.execute(
            "CREATE TABLE market (market_id TEXT PRIMARY KEY, fixture_id TEXT, "
            "market_name TEXT, selection_name TEXT, raw_odds REAL, prop_player TEXT, "
            "prop_type TEXT, prop_line REAL, scraped_at TEXT)"
        )
        con.execute(
            "INSERT INTO fixture (fixture_id, home_team, away_team) "
            "VALUES ('1', 'Diamond', 'Orange Sport')"
        )
        con.executemany(
            "INSERT INTO market (market_id, fixture_id, market_name, selection_name, raw_odds) "
            "VALUES (?, '1', 'Total Goals', ?, ?)",
            [(f"m{i}", s, p) for i, (s, p) in enumerate(markets)],
        )
        con.commit()
        con.close()

    return _write


def test_over_under_25_comes_from_the_25_line(stream):
    # Diamond vs Orange Sport, 2026-10-21, as stored once the scraper keeps lines.
    stream(
        [
            ("Total OVER  1.5", 1.32),
            ("Total UNDER  1.5", 2.95),
            ("Total OVER  2.5", 2.10),
            ("Total UNDER  2.5", 1.60),
            ("Total OVER  3.5", 3.75),
            ("Total UNDER  3.5", 1.20),
            ("OVER", 1.42),  # a first-half / Asian total: no line
            ("UNDER", 2.52),
        ]
    )
    odds = lpd.find_betarabia_odds("Diamond", "Orange Sport")
    assert odds["Over/Under 2.5"] == {"Over": 2.10, "Under": 1.60}


def test_other_lines_never_stand_in_for_25(stream):
    stream(
        [
            ("Total OVER  1.5", 1.32),
            ("Total UNDER  1.5", 2.95),
            ("Total OVER  3.5", 3.75),
            ("Total UNDER  3.5", 1.20),
        ]
    )
    odds = lpd.find_betarabia_odds("Diamond", "Orange Sport")
    assert odds["Over/Under 2.5"] == {}


@pytest.mark.parametrize("team_total", ["Dynamo Kyiv 2 OVER", "Club 2 de Mayo UNDER"])
def test_team_totals_with_digits_in_the_name_are_not_lines(stream, team_total):
    """Team totals arrive as '<Team> OVER'; a digit in the team name is not a line."""
    stream([(team_total, 1.85)])
    odds = lpd.find_betarabia_odds("Diamond", "Orange Sport")
    assert odds["Over/Under 2.0"] == {}
    assert odds["Over/Under 2.5"] == {}


def test_line_less_totals_are_ignored(stream):
    """Without a line there is no way to know which market a price belongs to."""
    stream([("Total OVER  2.5", 2.10), ("UNDER", 2.52), ("OVER", 1.42)])
    odds = lpd.find_betarabia_odds("Diamond", "Orange Sport")
    assert odds["Over/Under 2.5"] == {"Over": 2.10}
