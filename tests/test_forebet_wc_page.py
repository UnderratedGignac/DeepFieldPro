"""Tests for the Forebet World-Cup competition-page scraper.

Root cause (2026-07-10): Forebet's daily "predictions-for-today/tomorrow"
list pages do NOT carry World Cup fixtures — those live only on
/en/predictions-world/world-cup. The arena's Forebet-confirmation gate
fetched only the daily pages, so every WC semifinal sat unconfirmed and
the signal-only autopilot would have skipped the rest of the tournament.

The fixture file is the real WC page saved 2026-07-10. It contains BOTH
upcoming semifinals (Jul 10-12) and already-played matches (Jul 5-7) that
keep their old pre-match predictions — date filtering must exclude those,
otherwise a stale row for a repeat pairing could false-confirm a bet.
"""

import os

import pytest

from src.tipster_scraper import (
    _parse_forebet_wc_html,
    get_forebet_predictions,
    tipster_agrees,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "forebet_wc_20260710.html")


@pytest.fixture(scope="module")
def wc_html():
    with open(FIXTURE, encoding="utf-8") as f:
        return f.read()


def _pairs(preds):
    return [(p["home_team"], p["away_team"]) for p in preds]


def test_today_returns_only_spain_belgium(wc_html):
    preds = _parse_forebet_wc_html(wc_html, "2026-07-10")
    assert _pairs(preds) == [("Spain", "Belgium")]
    p = preds[0]
    assert p["predicted_side"] == "Home (1)"
    assert (p["prob_home"], p["prob_draw"], p["prob_away"]) == (45, 34, 21)
    assert p["date"] == "2026-07-10"
    assert p["source"] == "FOREBET"


def test_tomorrow_returns_norway_england_away(wc_html):
    preds = _parse_forebet_wc_html(wc_html, "2026-07-11")
    assert _pairs(preds) == [("Norway", "England")]
    assert preds[0]["predicted_side"] == "Away (2)"
    assert (preds[0]["prob_home"], preds[0]["prob_draw"], preds[0]["prob_away"]) == (27, 29, 44)


def test_day_plus_two_returns_argentina_home(wc_html):
    preds = _parse_forebet_wc_html(wc_html, "2026-07-12")
    assert _pairs(preds) == [("Argentina", "Switzerland")]
    assert preds[0]["predicted_side"] == "Home (1)"


def test_played_matches_are_date_excluded(wc_html):
    """Jul 5-7 rows (Portugal-Spain etc.) must never leak into Jul 10-12 queries."""
    for d in ("2026-07-10", "2026-07-11", "2026-07-12"):
        for pair in _pairs(_parse_forebet_wc_html(wc_html, d)):
            assert pair not in [
                ("Portugal", "Spain"),
                ("Brazil", "Norway"),
                ("Mexico", "England"),
                ("USA", "Belgium"),
                ("Argentina", "Egypt"),
                ("Switzerland", "Colombia"),
            ]


def test_agreement_gate_confirms_spain_home_only(wc_html):
    picks = _parse_forebet_wc_html(wc_html, "2026-07-10")
    assert tipster_agrees(picks, "Spain vs Belgium", "home") is True
    assert tipster_agrees(picks, "Spain vs Belgium", "draw") is False
    assert tipster_agrees(picks, "Spain vs Belgium", "away") is False
    # Tomorrow's match is not in today's picks — no cross-date confirmation.
    assert tipster_agrees(picks, "Norway vs England", "away") is False


def test_get_forebet_predictions_merges_wc_page(wc_html, monkeypatch):
    """The public entry point must return WC-page rows for the requested date
    without any network access, and must NOT serve the today-page for dates
    beyond tomorrow (the old silent-fallback bug)."""
    import datetime as _dt

    import src.tipster_scraper as ts

    # Freeze "today" to the fixture's capture date so the 2026-07-12 request is
    # reliably 2 days out ("beyond tomorrow") regardless of the wall-clock date
    # the suite runs on. (The fixture hardcodes Argentina vs Switzerland at
    # 2026-07-12, so the requested date can't be shifted — freeze today instead.)
    class _FrozenDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 10)

    monkeypatch.setattr(ts.datetime, "date", _FrozenDate)

    fetched_urls = []

    def fake_fetch(url, **kw):
        fetched_urls.append(url)
        if "predictions-world/world-cup" in url:
            return wc_html
        return "<html><body>no rcnt rows here</body></html>"

    monkeypatch.setattr(ts, "_fetch_forebet", fake_fetch)
    monkeypatch.setattr(ts, "_WC_HTML_CACHE", {"ts": 0.0, "html": None, "rows": 0})

    preds = ts.get_forebet_predictions("2026-07-12")
    assert _pairs(preds) == [("Argentina", "Switzerland")]
    # date is beyond tomorrow -> the daily today-page must not have been fetched
    assert all("for-today" not in u and "for-tomorrow" not in u for u in fetched_urls)
