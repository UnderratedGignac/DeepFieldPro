"""log_steam_bet gating (2026-07-14): steam paper bets are the strategy under
forward validation, so an EXPLICIT steam_betting_enabled=True must override
tipster_only_mode (research ledger only — never real money). With the flag
absent or False, tipster_only_mode blocks steam exactly as before."""
import sqlite3

import pytest

from tests._daemon_test_utils import import_daemon

lpd = import_daemon()

_SCHEMA = """
CREATE TABLE bet_log (
    bet_id TEXT PRIMARY KEY, match_id TEXT, player_id TEXT, market_type TEXT,
    line TEXT, side TEXT, entry_odds REAL, fair_odds REAL, edge_pct REAL,
    stake REAL, book TEXT, placed_at TEXT, lineup_drop_at TEXT, latency_ms INTEGER,
    closing_odds REAL, clv REAL, result TEXT DEFAULT 'OPEN', pnl REAL DEFAULT 0,
    regime TEXT, role_shift_flag INTEGER, bet_source TEXT, is_recommended INTEGER,
    model_version TEXT, fixture_id TEXT, league TEXT, clv_sharp REAL, best_odds REAL,
    best_book TEXT, signal_name TEXT, move_size REAL, monotonicity REAL, pinnacle_clv REAL,
    kickoff_time TEXT
)
"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    conn = sqlite3.connect(data / "bet_log.db")
    conn.executescript(_SCHEMA)
    conn.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(data))
    import src.bankroll_tracker as bt
    monkeypatch.setattr(bt, "register_bet", lambda stake, db_path=None: True)
    return data


def _settings(monkeypatch, **kw):
    base = {"steam_kelly_frac": 0, "steam_flat_stake": 1.0}
    base.update(kw)
    monkeypatch.setattr(lpd, "load_settings", lambda: dict(base))


def _rows(data):
    conn = sqlite3.connect(data / "bet_log.db")
    rows = list(conn.execute("SELECT bet_source, stake FROM bet_log"))
    conn.close()
    return rows


def test_explicit_steam_enable_overrides_tipster_only(env, monkeypatch):
    _settings(monkeypatch, tipster_only_mode=True, steam_betting_enabled=True)
    lpd.log_steam_bet("Alpha vs Beta", "1X2", "Home (1)", 2.0, 4.5, fixture_id="F9")
    assert _rows(env) == [("STEAM", 1.0)]


def test_steam_disabled_blocks_even_without_tipster_only(env, monkeypatch):
    _settings(monkeypatch, tipster_only_mode=False, steam_betting_enabled=False)
    lpd.log_steam_bet("Alpha vs Beta", "1X2", "Home (1)", 2.0, 4.5, fixture_id="F9")
    assert _rows(env) == []


def test_tipster_only_still_blocks_when_flag_absent(env, monkeypatch):
    # Legacy behavior preserved: no explicit opt-in -> tipster_only blocks steam.
    _settings(monkeypatch, tipster_only_mode=True)
    lpd.log_steam_bet("Alpha vs Beta", "1X2", "Home (1)", 2.0, 4.5, fixture_id="F9")
    assert _rows(env) == []
