"""Shared pytest fixtures for DeepFieldPro tests."""

import sqlite3
import tempfile
import os
import pytest


@pytest.fixture(autouse=True)
def _no_live_kambi_btts(monkeypatch):
    """find_betarabia_odds() asks Kambi for BTTS on every call; keep tests off
    the network. Tests that need BTTS prices monkeypatch their own."""
    import importlib

    monkeypatch.setattr(importlib.import_module("src.kambi_scraper"), "fetch_kambi_btts", lambda: {})


@pytest.fixture
def temp_bet_log(tmp_path):
    """Create a minimal bet_log SQLite DB in a temp directory.

    Returns the path to the DB file.
    """
    db_path = str(tmp_path / "bet_log.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE bet_log (
            bet_id      TEXT PRIMARY KEY,
            match_id    TEXT,
            player_id   TEXT,
            market_type TEXT,
            entry_odds  REAL,
            fair_odds   REAL,
            edge_pct    REAL,
            stake       REAL,
            result      TEXT DEFAULT 'OPEN',
            pnl         REAL DEFAULT 0,
            placed_at   TEXT,
            bet_source  TEXT,
            is_recommended INTEGER DEFAULT 1,
            line        TEXT,
            side        TEXT,
            fixture_id  TEXT,
            league      TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path
