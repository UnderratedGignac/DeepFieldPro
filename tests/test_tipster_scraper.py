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

import pytest

from src.tipster_scraper import _build_odds_map, _kambi_odds_for_side, _make_kambi_fixture_id


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
