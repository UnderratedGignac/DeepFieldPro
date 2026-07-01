"""Tests for bet filtering logic — league whitelist, AI gate, dedup, odds caps.

All filtering rules are tested in isolation without importing the full daemon
(which has heavyweight side-effects like DB connections, scrapers, and ML model
loading).  Each helper mirrors the exact logic in live_predictions_daemon.py so
that a future refactor of those helpers into a shared module can simply swap the
import.
"""

import sqlite3
import uuid
import pytest


# ---------------------------------------------------------------------------
# Pure helper functions — mirror the exact daemon logic being tested
# ---------------------------------------------------------------------------


def league_allowed(league: str | None, whitelist: list[str]) -> bool:
    """Return True when *league* passes the whitelist gate.

    Exact match only (case-insensitive, stripped).  An empty whitelist means
    "allow everything."  Mirrors the daemon code:

        _steam_wl_set = {w.lower().strip() for w in _steam_wl}
        _steam_league_ok = not _steam_wl or _league_lower in _steam_wl_set
    """
    if not whitelist:
        return True
    league_lower = (league or "").lower().strip()
    wl_set = {w.lower().strip() for w in whitelist}
    return league_lower in wl_set


def pinnacle_steam_odds_ok(odds: float, max_odds: float = 10.0) -> bool:
    """Return True when *odds* is within the PINNACLE_STEAM max-odds cap.

    Mirrors the daemon guard:
        odds <= _pin_steam_max_odds
    """
    return odds <= max_odds


def is_recommended(
    ev: float,
    prob: float,
    odds: float,
    market_allowed: bool,
    league_blocked: bool,
    draw_excluded: bool,
    conviction_ok: bool,
    steam_ok: bool,
    odds_fresh: bool,
    dc_covered: bool,
    steam_league_ok: bool,
    min_ev: float = 0.10,
    conf_threshold: float = 52.0,
    model_min_odds: float = 1.20,
    require_dc: bool = True,
) -> bool:
    """Mirror the daemon's is_recommended compound gate.

        is_recommended = (
            ev >= min_ev_threshold
            and prob >= conf_threshold
            and odds >= MODEL_MIN_ODDS
            and market_allowed
            and not league_blocked
            and not draw_excluded
            and conviction_ok
            and steam_ok
            and odds_fresh
            and (not require_dc or dc_covered)
            and _steam_league_ok
        )
    """
    return (
        ev >= min_ev
        and prob >= conf_threshold
        and odds >= model_min_odds
        and market_allowed
        and not league_blocked
        and not draw_excluded
        and conviction_ok
        and steam_ok
        and odds_fresh
        and (not require_dc or dc_covered)
        and steam_league_ok
    )


def cross_source_dedup(fixture_id: str | None, db_path: str) -> bool:
    """Return True if a new bet on *fixture_id* should be REJECTED due to dedup.

    Mirrors the daemon's cross-source dedup query in both log_steam_bet and
    log_ai_bet:

        SELECT COUNT(*) FROM bet_log WHERE fixture_id=? AND result='OPEN'

    Returns True (= reject) when there is already an open bet on this fixture.
    """
    if fixture_id is None:
        return False
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM bet_log WHERE fixture_id=? AND result='OPEN'",
        (str(fixture_id),),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def insert_open_bet(db_path: str, fixture_id: str, bet_source: str = "STEAM") -> str:
    """Insert a minimal OPEN bet row and return its bet_id."""
    bet_id = f"{bet_source}_{uuid.uuid4().hex[:10]}"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO bet_log
           (bet_id, match_id, player_id, market_type, entry_odds, fair_odds,
            edge_pct, stake, result, pnl, placed_at, bet_source,
            is_recommended, line, side, fixture_id, league)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            bet_id,
            "Team A vs Team B",
            "Team A vs Team B (Home)",
            "1X2",
            2.0,
            2.0,
            5.0,
            25.0,
            "OPEN",
            0.0,
            "2026-06-23T00:00:00",
            bet_source,
            1,
            "1X2",
            "Home",
            str(fixture_id),
            "Premier League",
        ),
    )
    conn.commit()
    conn.close()
    return bet_id


# ---------------------------------------------------------------------------
# WHITELIST — default list from data/settings.json
# ---------------------------------------------------------------------------

DEFAULT_WHITELIST = [
    "premier league",
    "la liga",
    "bundesliga",
    "serie a",
    "ligue 1",
    "eredivisie",
    "primeira liga",
    "championship",
    "scottish premiership",
    "champions league",
    "europa league",
    "conference league",
    "uefa champions league",
    "uefa europa league",
    "fifa world cup",
    "world cup",
    "a-league men",
    "major league soccer",
    "mls",
    "league of ireland premier division",
    "super lig",
    "premier liga",
    "russian premier league",
    "jupiler pro league",
    "pro league",
    "belgian pro league",
    "turkish super lig",
]


# ===========================================================================
# 1.  LEAGUE WHITELIST — exact match only
# ===========================================================================


class TestLeagueWhitelist:
    """Category 1 — league whitelist exact-match gate."""

    # --- leagues that MUST pass ---

    def test_premier_league_passes(self):
        assert league_allowed("Premier League", DEFAULT_WHITELIST) is True

    def test_premier_league_lowercase_passes(self):
        assert league_allowed("premier league", DEFAULT_WHITELIST) is True

    def test_premier_league_mixed_case_passes(self):
        assert league_allowed("PREMIER LEAGUE", DEFAULT_WHITELIST) is True

    def test_fifa_world_cup_passes(self):
        assert league_allowed("FIFA World Cup", DEFAULT_WHITELIST) is True

    def test_world_cup_passes(self):
        assert league_allowed("World Cup", DEFAULT_WHITELIST) is True

    def test_la_liga_passes(self):
        assert league_allowed("La Liga", DEFAULT_WHITELIST) is True

    def test_bundesliga_passes(self):
        assert league_allowed("Bundesliga", DEFAULT_WHITELIST) is True

    def test_champions_league_passes(self):
        assert league_allowed("Champions League", DEFAULT_WHITELIST) is True

    def test_mls_passes(self):
        assert league_allowed("MLS", DEFAULT_WHITELIST) is True

    # --- leagues that MUST fail ---

    def test_queensland_premier_league_fails(self):
        """Main bug: substring 'premier league' ≠ exact match 'Queensland Premier League'."""
        assert league_allowed("Queensland Premier League", DEFAULT_WHITELIST) is False

    def test_national_premier_league_fails(self):
        """Another substring trap — NPL is state-level Australian football."""
        assert league_allowed("National Premier League", DEFAULT_WHITELIST) is False

    def test_copa_rio_fails(self):
        assert league_allowed("Copa Rio", DEFAULT_WHITELIST) is False

    def test_reserve_league_fails(self):
        assert league_allowed("Reserve League", DEFAULT_WHITELIST) is False

    def test_empty_league_name_fails(self):
        """An empty or None league must not slip through when there is a whitelist."""
        assert league_allowed("", DEFAULT_WHITELIST) is False

    def test_none_league_name_fails(self):
        assert league_allowed(None, DEFAULT_WHITELIST) is False

    def test_whitespace_only_fails(self):
        assert league_allowed("   ", DEFAULT_WHITELIST) is False

    def test_partial_match_fails(self):
        """'bundesliga 2' is NOT in the whitelist — only 'bundesliga' is."""
        assert league_allowed("Bundesliga 2", DEFAULT_WHITELIST) is False

    def test_leading_trailing_whitespace_normalised(self):
        """Leading/trailing whitespace on the incoming value is stripped."""
        assert league_allowed("  Premier League  ", DEFAULT_WHITELIST) is True

    # --- empty whitelist = allow everything ---

    def test_empty_whitelist_allows_anything(self):
        assert league_allowed("Queensland Premier League", []) is True

    def test_empty_whitelist_allows_copa_rio(self):
        assert league_allowed("Copa Rio", []) is True

    def test_empty_whitelist_allows_empty_string(self):
        assert league_allowed("", []) is True


# ===========================================================================
# 2.  PINNACLE_STEAM MAX-ODDS CAP
# ===========================================================================


class TestPinnacleMaxOddsCap:
    """Category 2 — Pinnacle STEAM max-odds ceiling (default 10.0)."""

    def test_odds_2_passes(self):
        assert pinnacle_steam_odds_ok(2.0) is True

    def test_odds_5_passes(self):
        assert pinnacle_steam_odds_ok(5.0) is True

    def test_odds_exactly_at_cap_passes(self):
        """Boundary: odds == cap is allowed (<=, not <)."""
        assert pinnacle_steam_odds_ok(10.0) is True

    def test_odds_just_above_cap_fails(self):
        """10.01 must not slip past the cap."""
        assert pinnacle_steam_odds_ok(10.01) is False

    def test_odds_10_1_fails(self):
        assert pinnacle_steam_odds_ok(10.1) is False

    def test_portugal_uzbekistan_longshot_fails(self):
        """23.0 was the Portugal-Uzbekistan bug — extreme longshot must be blocked."""
        assert pinnacle_steam_odds_ok(23.0) is False

    def test_odds_100_fails(self):
        assert pinnacle_steam_odds_ok(100.0) is False

    def test_custom_cap_respected(self):
        """When the setting is changed the new cap is honoured."""
        assert pinnacle_steam_odds_ok(5.0, max_odds=4.0) is False
        assert pinnacle_steam_odds_ok(4.0, max_odds=4.0) is True
        assert pinnacle_steam_odds_ok(3.99, max_odds=4.0) is True


# ===========================================================================
# 3.  CROSS-SOURCE FIXTURE DEDUP
# ===========================================================================


class TestCrossSourceDedup:
    """Category 3 — one open bet per fixture across all sources."""

    def test_first_bet_on_fixture_is_allowed(self, temp_bet_log):
        rejected = cross_source_dedup("fixture_abc123", temp_bet_log)
        assert rejected is False

    def test_second_bet_same_fixture_different_source_rejected(self, temp_bet_log):
        """STEAM bet already open → AI bet on same fixture must be rejected."""
        insert_open_bet(temp_bet_log, "fixture_abc123", bet_source="STEAM")
        rejected = cross_source_dedup("fixture_abc123", temp_bet_log)
        assert rejected is True

    def test_second_bet_same_source_same_fixture_rejected(self, temp_bet_log):
        """Even same source must not double-up on the same fixture."""
        insert_open_bet(temp_bet_log, "fixture_abc123", bet_source="STEAM")
        rejected = cross_source_dedup("fixture_abc123", temp_bet_log)
        assert rejected is True

    def test_different_fixture_not_rejected(self, temp_bet_log):
        """Open bet on fixture A must not block fixture B."""
        insert_open_bet(temp_bet_log, "fixture_A", bet_source="STEAM")
        rejected = cross_source_dedup("fixture_B", temp_bet_log)
        assert rejected is False

    def test_none_fixture_id_never_rejected(self, temp_bet_log):
        """fixture_id=None means no dedup check (daemon behaviour)."""
        insert_open_bet(temp_bet_log, "fixture_abc123", bet_source="AI")
        rejected = cross_source_dedup(None, temp_bet_log)
        assert rejected is False

    def test_settled_bet_does_not_block_new_bet(self, temp_bet_log):
        """A SETTLED (result='WIN'/'LOSS') bet must not block a new open bet."""
        # Insert a settled bet manually
        conn = sqlite3.connect(temp_bet_log)
        conn.execute(
            """INSERT INTO bet_log
               (bet_id, match_id, player_id, market_type, entry_odds, fair_odds,
                edge_pct, stake, result, pnl, placed_at, bet_source,
                is_recommended, line, side, fixture_id, league)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "OLD_bet_001",
                "Team C vs Team D",
                "Team C vs Team D (Home)",
                "1X2",
                1.8,
                1.9,
                5.0,
                20.0,
                "WIN",      # SETTLED — result ≠ OPEN
                20.0,
                "2026-06-20T10:00:00",
                "STEAM",
                1,
                "1X2",
                "Home",
                "fixture_abc123",
                "Premier League",
            ),
        )
        conn.commit()
        conn.close()

        # The settled bet must NOT block a fresh open bet on the same fixture
        rejected = cross_source_dedup("fixture_abc123", temp_bet_log)
        assert rejected is False

    def test_multiple_different_fixtures_each_independent(self, temp_bet_log):
        """Dedup is per-fixture, not global."""
        insert_open_bet(temp_bet_log, "fixture_1", bet_source="STEAM")
        insert_open_bet(temp_bet_log, "fixture_2", bet_source="AI")

        assert cross_source_dedup("fixture_1", temp_bet_log) is True
        assert cross_source_dedup("fixture_2", temp_bet_log) is True
        assert cross_source_dedup("fixture_3", temp_bet_log) is False


# ===========================================================================
# 4.  AI GATE — is_recommended respects the league whitelist
# ===========================================================================


class TestAIGateLeagueWhitelist:
    """Category 4 — AI model is_recommended gate includes _steam_league_ok."""

    # Baseline "all other conditions are satisfied" kwargs
    PASSING_BASE = dict(
        ev=0.15,
        prob=60.0,
        odds=2.5,
        market_allowed=True,
        league_blocked=False,
        draw_excluded=False,
        conviction_ok=True,
        steam_ok=True,
        odds_fresh=True,
        dc_covered=True,
        min_ev=0.10,
        conf_threshold=52.0,
        model_min_odds=1.20,
        require_dc=True,
    )

    def test_premier_league_qualifies(self):
        result = is_recommended(
            **self.PASSING_BASE,
            steam_league_ok=league_allowed("Premier League", DEFAULT_WHITELIST),
        )
        assert result is True

    def test_la_liga_qualifies(self):
        result = is_recommended(
            **self.PASSING_BASE,
            steam_league_ok=league_allowed("La Liga", DEFAULT_WHITELIST),
        )
        assert result is True

    def test_world_cup_qualifies(self):
        result = is_recommended(
            **self.PASSING_BASE,
            steam_league_ok=league_allowed("FIFA World Cup", DEFAULT_WHITELIST),
        )
        assert result is True

    def test_queensland_premier_league_rejected(self):
        """The main substring bug: QLD PL must fail the AI gate too."""
        result = is_recommended(
            **self.PASSING_BASE,
            steam_league_ok=league_allowed("Queensland Premier League", DEFAULT_WHITELIST),
        )
        assert result is False

    def test_copa_rio_rejected(self):
        result = is_recommended(
            **self.PASSING_BASE,
            steam_league_ok=league_allowed("Copa Rio", DEFAULT_WHITELIST),
        )
        assert result is False

    def test_reserve_league_rejected(self):
        result = is_recommended(
            **self.PASSING_BASE,
            steam_league_ok=league_allowed("Reserve League", DEFAULT_WHITELIST),
        )
        assert result is False

    def _call(self, **overrides):
        """Helper: merge PASSING_BASE with overrides and call is_recommended."""
        kwargs = {**self.PASSING_BASE, **overrides}
        return is_recommended(**kwargs)

    def test_low_ev_rejected(self):
        """EV below threshold blocks recommendation regardless of league."""
        result = self._call(ev=0.05, steam_league_ok=True)
        assert result is False

    def test_dc_not_covered_rejected_when_required(self):
        """require_dc=True + dc_covered=False must block the pick."""
        result = self._call(dc_covered=False, require_dc=True, steam_league_ok=True)
        assert result is False

    def test_dc_not_covered_allowed_when_not_required(self):
        """require_dc=False lets picks through even without DC coverage."""
        result = self._call(dc_covered=False, require_dc=False, steam_league_ok=True)
        assert result is True

    def test_low_conviction_rejected(self):
        """conviction_ok=False (model/market diverge too much) blocks the pick."""
        result = self._call(conviction_ok=False, steam_league_ok=True)
        assert result is False

    def test_stale_odds_rejected(self):
        result = self._call(odds_fresh=False, steam_league_ok=True)
        assert result is False

    def test_draw_excluded_blocks_draw_side(self):
        result = self._call(draw_excluded=True, steam_league_ok=True)
        assert result is False

    def test_blocked_league_overrides_whitelist(self):
        """league_blocked=True (explicit blocklist) takes priority over whitelist."""
        result = self._call(league_blocked=True, steam_league_ok=True)
        assert result is False


# ===========================================================================
# 5.  SETTINGS DEFAULTS — sanity checks that settings.json values match
#     the hard-coded defaults in the filtering logic
# ===========================================================================


class TestSettingsDefaults:
    """Category 5 — verify that data/settings.json encodes the expected defaults."""

    def _load_settings(self):
        import json
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "data", "settings.json"
        )
        with open(path) as f:
            return json.load(f)

    def test_ai_real_staking_disabled_by_default(self):
        s = self._load_settings()
        assert s.get("ai_real_staking_enabled", False) is False

    def test_require_dc_coverage_enabled_by_default(self):
        s = self._load_settings()
        assert s.get("require_dc_coverage", True) is True

    def test_pinnacle_steam_max_odds_is_10(self):
        s = self._load_settings()
        assert s.get("pinnacle_steam_max_odds", 10.0) == pytest.approx(10.0)

    def test_steam_league_whitelist_is_non_empty(self):
        s = self._load_settings()
        wl = s.get("steam_league_whitelist", [])
        assert len(wl) > 0, "Whitelist must not be empty"

    def test_queensland_not_in_whitelist(self):
        """Guard that nobody accidentally adds Queensland back."""
        s = self._load_settings()
        wl = {w.lower() for w in s.get("steam_league_whitelist", [])}
        assert "queensland premier league" not in wl

    def test_national_premier_league_not_in_whitelist(self):
        s = self._load_settings()
        wl = {w.lower() for w in s.get("steam_league_whitelist", [])}
        assert "national premier league" not in wl

    def test_fifa_world_cup_in_whitelist(self):
        s = self._load_settings()
        wl = {w.lower() for w in s.get("steam_league_whitelist", [])}
        assert "fifa world cup" in wl
