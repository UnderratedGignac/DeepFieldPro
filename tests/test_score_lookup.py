"""Tests for tools/score_lookup.py's deep-lookup fuzzy result matchers.

Regression (2026-07-12): the "flashscore-feed-fuzzy" source in
_fs_feed_fuzzy() has no squad-level guard, so a senior-team bet's name can
fuzzy-match a differently-leveled Flashscore feed row (e.g. a club's U21
side). It matched "Melbourne City NPL vs Heidelberg Utd" to Flashscore's
"Melbourne City U21 vs Heidelberg Utd" and settled the bet from it
(bet TIP_FORE_27547265_cd717295, settle_source='deep-lookup',
settle_reason='flashscore-feed-fuzzy'). That grade happened to be correct
(the NPL side is actually the U21 squad), but the matcher had no mechanism
to stop a genuine cross-level collision -- the same bug class fixed for the
daemon's sim2 pass (src/live_predictions_daemon.py, see
test_sim2_fallback_respects_level_guard in test_settlement_grading.py) via
src.name_matching._level_signature().
"""

import sys
import types

import tools.score_lookup as score_lookup


def _stub_flashscore_feed(monkeypatch, results):
    mod = types.ModuleType("flashscore_scraper")
    mod.get_finished_results = lambda dates=None: results
    monkeypatch.setitem(sys.modules, "flashscore_scraper", mod)


class TestFeedFuzzyLevelGuard:
    def test_rejects_cross_level_match(self, monkeypatch):
        """A senior-team bet must never be settled off a same-club,
        different-squad-level feed row, even when the name text is close
        enough to clear the plain fuzzy-similarity thresholds."""
        _stub_flashscore_feed(
            monkeypatch,
            {"Melbourne City U21 vs Heidelberg Utd": (2, 2)},
        )
        assert score_lookup._fs_feed_fuzzy("Melbourne City NPL", "Heidelberg Utd") is None

    def test_still_matches_same_level(self, monkeypatch):
        """Sanity check: same-level fuzzy matching must keep working after
        the level guard is added."""
        _stub_flashscore_feed(
            monkeypatch,
            {"Melbourne City vs Heidelberg Utd": (2, 2)},
        )
        assert score_lookup._fs_feed_fuzzy("Melbourne City NPL", "Heidelberg Utd") == (2, 2)

    def test_rejects_cross_level_reversed_orientation(self, monkeypatch):
        """The reversed-orientation branch (feed lists teams swapped vs the
        bet) must apply the same level guard as the normal orientation."""
        _stub_flashscore_feed(
            monkeypatch,
            {"Heidelberg Utd vs Melbourne City U21": (2, 2)},
        )
        assert score_lookup._fs_feed_fuzzy("Melbourne City NPL", "Heidelberg Utd") is None


class TestRowMatchesOpponentLevelGuard:
    """_fs_row_matches_opponent() backs the flashscore-home/away team-page
    strategies (2 and 3 in lookup_score()) -- same collision class as the
    feed-fuzzy source, just scoped to a single scraped results row."""

    def test_rejects_cross_level_opponent(self):
        row = {"home": "Melbourne City", "away": "Heidelberg Utd U21"}
        assert score_lookup._fs_row_matches_opponent(row, "Heidelberg Utd") is False

    def test_accepts_same_level_opponent(self):
        row = {"home": "Melbourne City", "away": "Heidelberg Utd"}
        assert score_lookup._fs_row_matches_opponent(row, "Heidelberg Utd") is True
