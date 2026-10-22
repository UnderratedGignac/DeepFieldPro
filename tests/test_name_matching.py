"""
Unit tests for src/name_matching.py (extracted 2026-07-10 from
live_predictions_daemon.py). Includes the real cases that motivated
the fixture_verifier.py phantom-detection fix.
"""

import pytest

from src.name_matching import get_match_score, fuzzy_match_teams, best_fixture_match


def test_identical_names_score_one():
    assert get_match_score("Real Oruro", "Real Oruro") == 1.0


def test_empty_or_none_scores_zero():
    assert get_match_score("", "Real Oruro") == 0.0
    assert get_match_score(None, "Real Oruro") == 0.0
    assert get_match_score("Real Oruro", None) == 0.0


def test_non_string_input_scores_zero():
    assert get_match_score(123, "Real Oruro") == 0.0


def test_noise_suffix_stripped_fc_city_united():
    # "Linfield FC" vs "Linfield" -- "fc" is a noise token, both reduce to {"linfield"}
    assert get_match_score("Linfield FC", "Linfield") >= 0.9


def test_country_code_suffix_still_matches_reasonably():
    """
    The real case that motivated fixture_verifier.py's fix: Flashscore tags
    team names with a parenthetical country code ("Kalju (Est)") that isn't in
    the noise-word set. Confirms get_match_score alone already clears the
    0.5 threshold used elsewhere (settle_open_bets, best_fixture_match) --
    the false-positive-phantom bug was in fixture_verifier's SEPARATE
    Playwright-based check, not in this scorer.
    """
    assert get_match_score("Nõmme Kalju", "Kalju (Est)") >= 0.5
    assert get_match_score("Linfield FC", "Linfield (Nir)") >= 0.5


def test_accent_stripping():
    assert get_match_score("Nõmme Kalju", "Nomme Kalju") == 1.0


def test_alias_mapping_ivory_coast():
    assert get_match_score("Cote d'Ivoire", "Ivory Coast") >= 0.9


def test_fuzzy_match_teams_threshold():
    assert fuzzy_match_teams("Real Oruro", "Real Oruro") is True
    assert fuzzy_match_teams("Real Oruro", "Manchester United") is False


def test_completely_unrelated_names_score_low():
    assert get_match_score("Real Oruro", "Manchester United") < 0.5


# ---------------------------------------------------------------------------
# best_fixture_match() -- used by the fixture_verifier.py fix
# ---------------------------------------------------------------------------
def test_best_fixture_match_finds_real_oruro():
    finished = {
        "Real Oruro vs Universitario de Vinto": (2, 1),
        "Some Other Match vs Unrelated Team": (0, 0),
    }
    result = best_fixture_match("Real Oruro", "Universitario de Vinto", finished)
    assert result is not None
    name, score, total = result
    assert name == "Real Oruro vs Universitario de Vinto"
    assert score == (2, 1)


def test_best_fixture_match_handles_country_code_suffixes():
    finished = {"Kalju (Est) vs Linfield (Nir)": (1, 0)}
    result = best_fixture_match("Nõmme Kalju", "Linfield FC", finished)
    assert result is not None
    assert result[1] == (1, 0)


def test_best_fixture_match_handles_reversed_orientation():
    finished = {"Linfield (Nir) vs Kalju (Est)": (0, 2)}  # away/home swapped vs the bet
    result = best_fixture_match("Nõmme Kalju", "Linfield FC", finished)
    assert result is not None
    name, score, total = result
    assert "[reversed]" in name
    # score must be re-oriented to (kalju, linfield) = (2, 0), not the raw (0, 2)
    assert score == (2, 0)


def test_best_fixture_match_returns_none_when_no_candidate_clears_threshold():
    finished = {"Manchester United vs Chelsea": (1, 1)}
    result = best_fixture_match("Real Oruro", "Universitario de Vinto", finished)
    assert result is None


def test_best_fixture_match_empty_dict_returns_none():
    assert best_fixture_match("Real Oruro", "Universitario de Vinto", {}) is None


# ---------------------------------------------------------------------------
# Age-group / reserve level guard (regression for the 2026-07-11 forensics:
# 'u23'/'u20' were stripped as noise, so a U23 team tokenized identically to
# its senior twin -> the settlement matcher graded U23 bets against senior
# results, e.g. Green Gully SC U23 mis-graded against the senior 1-3, and
# Canberra Juventus U23 vs the senior fixture. A level mismatch must score 0.)
# ---------------------------------------------------------------------------
def test_u23_does_not_match_senior():
    assert get_match_score("Green Gully SC U23", "Green Gully") < 0.5
    assert get_match_score("Canberra Juventus U23", "Canberra Juventus") < 0.5


def test_u23_matches_u23():
    assert get_match_score("Green Gully SC U23", "Green Gully U23") >= 0.9


def test_different_age_groups_do_not_match():
    # U21 and U23 are distinct competitions — must not cross-settle
    assert get_match_score("Chelsea U21", "Chelsea U23") < 0.5


def test_reserves_do_not_match_senior():
    assert get_match_score("River Plate Reserves", "River Plate") < 0.5
    # roman-numeral reserve marker (Bayern II is the reserve side, not Bayern)
    assert get_match_score("Bayern Munich II", "Bayern Munich") < 0.5


def test_reserves_match_reserves_singular_or_plural():
    assert get_match_score("River Plate Reserves", "River Plate Reserve") >= 0.9


def test_juniors_in_club_name_is_not_a_youth_marker():
    # "Juniors" is part of Boca's proper name, not an age level — must not
    # be mistaken for a youth marker and must still match itself.
    assert get_match_score("Boca Juniors", "Boca Juniors") == 1.0
    assert get_match_score("Boca Juniors", "Boca Juniors CABJ") >= 0.8


def test_best_fixture_match_rejects_senior_result_for_u23_bet():
    # The Green Gully case: only the senior result exists in the feed; a U23
    # bet must NOT be settled against it (better OPEN than wrongly graded).
    finished = {"Green Gully vs Altona Magic": (1, 3)}
    result = best_fixture_match("Green Gully SC U23", "Altona Magic SC U23", finished)
    assert result is None


def test_best_fixture_match_accepts_matching_u23_result():
    finished = {"Green Gully U23 vs Altona Magic U23": (2, 0)}
    result = best_fixture_match("Green Gully SC U23", "Altona Magic SC U23", finished)
    assert result is not None
    assert result[1] == (2, 0)
