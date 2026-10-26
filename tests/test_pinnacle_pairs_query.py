"""The Pinnacle name-pair query must ride the ts index, not scan the table.

2026-10-26: `SELECT DISTINCT home_team, away_team ... WHERE ts >= ?` let SQLite
satisfy DISTINCT through idx_soh_teams and full-SCAN sharp_odds_history,
checking ts row by row. On a partly paged-out server that took minutes, ran
every 5 minutes (cache TTL), and kept the prediction loop silent long enough
for the watchdog to restart it twice overnight (01:43, 05:03). Same failure
class as the 2026-07-11 wc_upcoming_scraper ORDER BY scan.
"""

import importlib
import sqlite3
import time

pv = importlib.import_module("tools.pinnacle_value")

SCHEMA = """
CREATE TABLE sharp_odds_history (
    match_key TEXT, home_team TEXT, away_team TEXT, league TEXT,
    selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL
)
"""
# The indexes pinnacle_feed.py creates on the live table.
INDEXES = (
    "CREATE INDEX idx_soh_ts ON sharp_odds_history(ts)",
    "CREATE INDEX idx_soh_teams ON sharp_odds_history(home_team, away_team, selection)",
)


def _db():
    con = sqlite3.connect(":memory:")
    con.execute(SCHEMA)
    for sql in INDEXES:
        con.execute(sql)
    return con


def test_pairs_query_searches_the_ts_index():
    con = _db()
    plan = " ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + pv._PIN_PAIRS_SQL, (0.0,)))
    assert "SEARCH sharp_odds_history USING INDEX idx_soh_ts" in plan
    assert "idx_soh_teams" not in plan


def test_pairs_query_returns_distinct_recent_pairs_only():
    con = _db()
    now = time.time()
    rows = [
        ("Ajax", "PSV", "home", now - 60),
        ("Ajax", "PSV", "away", now - 30),           # same pair, other selection
        ("Celtic", "Rangers", "home", now - 120),
        ("Old FC", "Gone FC", "home", now - 50_000),  # outside the 12h window
    ]
    con.executemany(
        "INSERT INTO sharp_odds_history (home_team, away_team, selection, ts) VALUES (?,?,?,?)",
        rows,
    )
    got = sorted(con.execute(pv._PIN_PAIRS_SQL, (now - 43200.0,)).fetchall())
    assert got == [("Ajax", "PSV"), ("Celtic", "Rangers")]
