"""A youth fixture must never be priced against the senior match on Pinnacle.

UEFA Youth League games mirror the Champions League fixtures on the same day.
On 2026-10-21 "Lille (U-19) vs Galatasaray (U-19)" fuzzy-matched Pinnacle's
senior "Lille vs Galatasaray" and logged a +14.5% "edge" on Under 2.5 that was
just the gap between two different matches. name_matching._level_signature()
already guards get_match_score() against this; the Pinnacle matchers used raw
SequenceMatcher and skipped it.
"""

import importlib
import time

import pytest

pv = importlib.import_module("tools.pinnacle_value")

SENIOR = {"over": 1.68, "under": 2.28, "p_over": 0.5757, "p_under": 0.4243}
YOUTH = {"over": 1.80, "under": 2.00, "p_over": 0.52, "p_under": 0.48}


def test_youth_fixture_does_not_match_the_senior_totals():
    assert pv._fuzzy_match_ou25(
        "Lille (U-19)", "Galatasaray (U-19)", {"Lille vs Galatasaray": SENIOR}
    ) is None


def test_youth_fixture_matches_the_youth_totals():
    got = pv._fuzzy_match_ou25(
        "Lille (U-19)",
        "Galatasaray (U-19)",
        {"Lille vs Galatasaray": SENIOR, "Lille U19 vs Galatasaray U19": YOUTH},
    )
    assert got is YOUTH


def test_senior_fixture_still_matches_across_name_variants():
    got = pv._fuzzy_match_ou25(
        "Inter Milan", "Shakhtar Donetsk", {"Internazionale vs Shakhtar Donetsk": SENIOR}
    )
    assert got is SENIOR


@pytest.fixture
def pin_pairs(monkeypatch):
    def _set(pairs):
        monkeypatch.setitem(pv._PIN_PAIRS_CACHE, "ts", time.time())
        monkeypatch.setitem(pv._PIN_PAIRS_CACHE, "pairs", pairs)

    return _set


def test_1x2_pair_resolution_respects_squad_level(pin_pairs):
    pin_pairs([("Lille", "Galatasaray")])
    assert pv._fuzzy_resolve_pair("Lille (U-19)", "Galatasaray (U-19)") is None


def test_1x2_pair_resolution_still_finds_same_level(pin_pairs):
    pin_pairs([("Lille", "Galatasaray"), ("Lille U19", "Galatasaray U19")])
    assert pv._fuzzy_resolve_pair("Lille (U-19)", "Galatasaray (U-19)") == (
        "Lille U19",
        "Galatasaray U19",
    )
