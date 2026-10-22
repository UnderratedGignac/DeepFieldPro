"""Parsing tests for src/free_results_scraper.py (settlement results feed).

HTTP is fully mocked via monkeypatched requests.get. Covers:
- _espn_day: completed-only filtering, score parsing, malformed events skipped
- _tsdb_day: the finished-status whitelist — LIVE matches must be excluded
  (regression guard for the "Spain 0-0 Cape Verde settled while live" bug)
- _results_for_date: ESPN overrides TheSportsDB on overlap + per-date caching
- get_finished_results: merges dates, swallows per-date errors
"""

import pytest

import src.free_results_scraper as frs


class FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _espn_event(home, away, hs, as_, completed=True):
    return {
        "competitions": [
            {
                "status": {"type": {"completed": completed}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": str(hs),
                        "team": {"displayName": home},
                    },
                    {
                        "homeAway": "away",
                        "score": str(as_),
                        "team": {"displayName": away},
                    },
                ],
            }
        ]
    }


def _tsdb_event(home, away, hs, as_, status="FT"):
    return {
        "strHomeTeam": home,
        "strAwayTeam": away,
        "intHomeScore": hs,
        "intAwayScore": as_,
        "strStatus": status,
    }


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(frs, "_cache", {})


def _mock_get(monkeypatch, espn_events=(), tsdb_events=(), counter=None):
    """requests.get stub: first ESPN league URL returns espn_events, all other
    ESPN leagues return empty; the TSDB URL returns tsdb_events."""
    first_league = frs.ESPN_LEAGUES[0]

    def fake_get(url, headers=None, params=None, timeout=None):
        if counter is not None:
            counter.append(url)
        if url.startswith(frs._TSDB_BASE):
            return FakeResp({"events": list(tsdb_events)})
        if f"/{first_league}/" in url:
            return FakeResp({"events": list(espn_events)})
        return FakeResp({"events": []})

    monkeypatch.setattr(frs.requests, "get", fake_get)


# ---------------------------------------------------------------------------
# _espn_day
# ---------------------------------------------------------------------------

class TestEspnDay:
    def test_completed_match_parsed(self, monkeypatch):
        _mock_get(monkeypatch, espn_events=[_espn_event("Arsenal", "Chelsea", 2, 1)])
        out = frs._espn_day("2026-07-09")
        assert out == {"Arsenal vs Chelsea": (2, 1)}

    def test_not_completed_excluded(self, monkeypatch):
        """Never settle from a live/scheduled match."""
        _mock_get(
            monkeypatch,
            espn_events=[_espn_event("Arsenal", "Chelsea", 1, 0, completed=False)],
        )
        assert frs._espn_day("2026-07-09") == {}

    def test_unparseable_score_skipped(self, monkeypatch):
        ev = _espn_event("Arsenal", "Chelsea", 2, 1)
        ev["competitions"][0]["competitors"][0]["score"] = "N/A"
        _mock_get(monkeypatch, espn_events=[ev])
        assert frs._espn_day("2026-07-09") == {}

    def test_wrong_competitor_count_skipped(self, monkeypatch):
        ev = _espn_event("Arsenal", "Chelsea", 2, 1)
        ev["competitions"][0]["competitors"].pop()
        _mock_get(monkeypatch, espn_events=[ev])
        assert frs._espn_day("2026-07-09") == {}

    def test_http_error_league_skipped(self, monkeypatch):
        def fake_get(url, **kwargs):
            return FakeResp({}, status_code=503)

        monkeypatch.setattr(frs.requests, "get", fake_get)
        assert frs._espn_day("2026-07-09") == {}


# ---------------------------------------------------------------------------
# _tsdb_day — finished-status whitelist
# ---------------------------------------------------------------------------

class TestTsdbDay:
    def test_ft_match_included(self, monkeypatch):
        _mock_get(monkeypatch, tsdb_events=[_tsdb_event("Spain", "Cape Verde", 3, 0)])
        assert frs._tsdb_day("2026-07-09") == {"Spain vs Cape Verde": (3, 0)}

    @pytest.mark.parametrize("live_status", ["1H", "2H", "HT", "ET", "LIVE", ""])
    def test_live_or_unknown_status_excluded(self, monkeypatch, live_status):
        """Regression guard: TheSportsDB also returns LIVE matches with a
        current score; treating those as final settled bets mid-match."""
        _mock_get(
            monkeypatch,
            tsdb_events=[_tsdb_event("Spain", "Cape Verde", 0, 0, status=live_status)],
        )
        assert frs._tsdb_day("2026-07-09") == {}

    def test_status_is_case_insensitive(self, monkeypatch):
        _mock_get(
            monkeypatch,
            tsdb_events=[_tsdb_event("A", "B", 1, 0, status="Match Finished")],
        )
        assert frs._tsdb_day("2026-07-09") == {"A vs B": (1, 0)}

    def test_missing_scores_skipped(self, monkeypatch):
        _mock_get(
            monkeypatch,
            tsdb_events=[
                _tsdb_event("A", "B", None, 1),
                _tsdb_event("C", "D", "", 1),
                _tsdb_event("E", "F", 2, 1),
            ],
        )
        assert frs._tsdb_day("2026-07-09") == {"E vs F": (2, 1)}

    def test_scores_coerced_to_int(self, monkeypatch):
        _mock_get(monkeypatch, tsdb_events=[_tsdb_event("A", "B", "2", "1")])
        assert frs._tsdb_day("2026-07-09") == {"A vs B": (2, 1)}


# ---------------------------------------------------------------------------
# _results_for_date — merge precedence + cache
# ---------------------------------------------------------------------------

class TestResultsForDate:
    def test_espn_overrides_tsdb_on_overlap(self, monkeypatch):
        _mock_get(
            monkeypatch,
            espn_events=[_espn_event("Arsenal", "Chelsea", 2, 1)],
            tsdb_events=[_tsdb_event("Arsenal", "Chelsea", 9, 9)],
        )
        out = frs._results_for_date("2026-07-09")
        assert out["Arsenal vs Chelsea"] == (2, 1)  # ESPN is authoritative

    def test_sources_merge(self, monkeypatch):
        _mock_get(
            monkeypatch,
            espn_events=[_espn_event("Arsenal", "Chelsea", 2, 1)],
            tsdb_events=[_tsdb_event("Obscure FC", "Minor SK", 0, 0)],
        )
        out = frs._results_for_date("2026-07-09")
        assert out == {
            "Arsenal vs Chelsea": (2, 1),
            "Obscure FC vs Minor SK": (0, 0),
        }

    def test_second_call_served_from_cache(self, monkeypatch):
        calls = []
        _mock_get(
            monkeypatch,
            espn_events=[_espn_event("A", "B", 1, 0)],
            counter=calls,
        )
        first = frs._results_for_date("2026-07-09")
        n_after_first = len(calls)
        second = frs._results_for_date("2026-07-09")
        assert second == first
        assert len(calls) == n_after_first  # no new HTTP traffic

    def test_cache_is_per_date(self, monkeypatch):
        calls = []
        _mock_get(monkeypatch, counter=calls)
        frs._results_for_date("2026-07-09")
        n_after_first = len(calls)
        frs._results_for_date("2026-07-08")
        assert len(calls) == 2 * n_after_first


# ---------------------------------------------------------------------------
# get_finished_results
# ---------------------------------------------------------------------------

class TestGetFinishedResults:
    def test_merges_requested_dates(self, monkeypatch):
        seen = []

        def fake(date_str):
            seen.append(date_str)
            return {f"M{date_str} vs X": (1, 0)}

        monkeypatch.setattr(frs, "_results_for_date", fake)
        out = frs.get_finished_results(dates=["2026-07-08", "2026-07-09"])
        assert seen == ["2026-07-08", "2026-07-09"]
        assert len(out) == 2

    def test_per_date_error_swallowed(self, monkeypatch):
        def fake(date_str):
            if date_str == "bad":
                raise RuntimeError("feed down")
            return {"A vs B": (1, 1)}

        monkeypatch.setattr(frs, "_results_for_date", fake)
        out = frs.get_finished_results(dates=["bad", "2026-07-09"])
        assert out == {"A vs B": (1, 1)}
