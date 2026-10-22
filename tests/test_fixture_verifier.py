"""
Unit tests for the fixture_verifier.py phantom-detection fix (2026-07-10).

Bug: verify() relied solely on a Flashscore team-search + Playwright
schedule-page check, which has different/narrower coverage than the actual
merged settlement sources and produced false PHANTOM verdicts for real,
already-scoreable fixtures (e.g. "Real Oruro vs Universitario de Vinto").

Fix: verify() now accepts an optional finished_matches dict and returns REAL
immediately if a confident match exists there, without ever calling
Flashscore/Playwright.
"""

import pytest

from src.fixture_verifier import verify


def test_real_oruro_case_no_longer_false_positive_phantom():
    """The exact real-world case that motivated this fix."""
    finished_matches = {"Real Oruro vs Universitario de Vinto": (2, 1)}
    result = verify("Real Oruro", "Universitario de Vinto", finished_matches=finished_matches)
    assert result["verdict"] == "REAL"
    assert result["home_found"] is True
    assert result["away_found"] is True


def test_country_code_suffix_case_resolves_real():
    """Kalju (Est) vs Linfield (Nir) -- another real case from this session."""
    finished_matches = {"Kalju (Est) vs Linfield (Nir)": (1, 0)}
    result = verify("Nõmme Kalju", "Linfield FC", finished_matches=finished_matches)
    assert result["verdict"] == "REAL"


def test_finished_matches_short_circuits_before_any_network_call(monkeypatch):
    """
    When a confident match exists in finished_matches, verify() must return
    REAL without ever calling _search_team() (i.e. no network/Flashscore
    request at all) -- this is what makes the fix fast, not just correct.
    """
    called = []

    def _fail_if_called(name):
        called.append(name)
        raise AssertionError("should not reach Flashscore search when finished_matches has a match")

    monkeypatch.setattr("src.fixture_verifier._search_team", _fail_if_called)
    finished_matches = {"Real Oruro vs Universitario de Vinto": (2, 1)}
    result = verify("Real Oruro", "Universitario de Vinto", finished_matches=finished_matches)
    assert result["verdict"] == "REAL"
    assert called == []


def test_no_finished_matches_falls_back_to_search(monkeypatch):
    """
    With finished_matches=None (or empty), verify() must still fall back to
    the original Flashscore search+schedule check -- backward compatible for
    callers that don't have a pre-fetched results dict.
    """
    monkeypatch.setattr("src.fixture_verifier._search_team", lambda name: None)
    result = verify("Totally Fake Team A", "Totally Fake Team B", finished_matches=None)
    assert result["verdict"] == "PHANTOM"
    assert "Neither team exists" in result["detail"]


def test_empty_finished_matches_dict_falls_back_to_search(monkeypatch):
    monkeypatch.setattr("src.fixture_verifier._search_team", lambda name: None)
    result = verify("Totally Fake Team A", "Totally Fake Team B", finished_matches={})
    assert result["verdict"] == "PHANTOM"


def test_finished_matches_with_no_matching_fixture_falls_back(monkeypatch):
    """A finished_matches dict that doesn't contain THIS fixture must still fall through to search."""
    monkeypatch.setattr("src.fixture_verifier._search_team", lambda name: None)
    finished_matches = {"Manchester United vs Chelsea": (1, 1)}
    result = verify("Totally Fake Team A", "Totally Fake Team B", finished_matches=finished_matches)
    assert result["verdict"] == "PHANTOM"
