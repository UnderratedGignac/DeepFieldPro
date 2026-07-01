"""Audit leagues in recent bets and steam signals."""
import sqlite3

# Check what leagues appear in bet_log
print("=== Leagues in bet_log ===")
conn = sqlite3.connect("data/bet_log.db")
cur = conn.cursor()
cur.execute("SELECT placed_at, match_id, league, entry_odds, stake, result, pnl, bet_source FROM bet_log ORDER BY placed_at DESC LIMIT 20")
for r in cur.fetchall():
    print(r)

print("\n=== Steam signals in completed_fixtures.db ===")
conn2 = sqlite3.connect("data/deepfield_browser_data/completed_fixtures.db")
cur2 = conn2.cursor()
cur2.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur2.fetchall()])
try:
    cur2.execute("SELECT * FROM steam_signals ORDER BY detected_at DESC LIMIT 20")
    cols2 = [d[0] for d in cur2.description]
    print(f"Cols: {cols2}")
    for r in cur2.fetchall():
        print(r)
except Exception as e:
    print(f"steam_signals error: {e}")
conn2.close()

print("\n=== odds_stream.db fixture leagues (today) ===")
conn3 = sqlite3.connect("data/odds_stream.db")
cur3 = conn3.cursor()
cur3.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur3.fetchall()])
try:
    cur3.execute("""
        SELECT DISTINCT tournament_name, home_team, away_team, kickoff_date
        FROM fixture
        WHERE kickoff_date >= '2026-06-22'
        ORDER BY kickoff_date DESC LIMIT 30
    """)
    for r in cur3.fetchall():
        print(r)
except Exception as e:
    print(f"fixture error: {e}")

print("\n=== sharp_odds_history — leagues with moves ===")
try:
    cur3.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur3.fetchall()]
    if "sharp_odds_history" in tables:
        cur3.execute("""
            SELECT DISTINCT home, away
            FROM sharp_odds_history
            WHERE ts >= datetime('now','-2 days')
            ORDER BY ts DESC LIMIT 40
        """)
        for r in cur3.fetchall():
            print(r)
except Exception as e:
    print(f"sharp_odds_history error: {e}")
conn3.close()

# Check whitelist matching bug
print("\n=== WHITELIST BUG CHECK ===")
whitelist = ["premier league", "la liga", "bundesliga", "serie a", "ligue 1",
             "eredivisie", "primeira liga", "championship",
             "scottish premiership", "champions league", "europa league",
             "fifa world cup", "world cup"]
test_leagues = [
    "NPL Queensland", "National Premier Leagues Queensland",
    "Australia - NPL Queensland", "Logan Lightning",
    "Queensland Premier League", "national premier leagues",
    "A-League Men", "Portuguese Primeira Liga", "FA Cup"
]
for league in test_leagues:
    league_lower = league.lower()
    matched = [w for w in whitelist if w in league_lower]
    ok = bool(matched)
    print(f"  '{league}' -> ok={ok} matched={matched}")
