"""System health check — scraper freshness, open bets, and live state."""

import sqlite3, json, sys, io, os, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.join(os.path.dirname(__file__), "..")

# 1. Dashboard state summary
print("=== Dashboard state ===")
try:
    with open(
        os.path.join(BASE, "data", "todays_dashboard_state.json"), encoding="utf-8"
    ) as f:
        state = json.load(f)
    statuses = {}
    for item in state:
        s = item.get("status_code", "?")
        statuses[s] = statuses.get(s, 0) + 1
    print(f"Total matches: {len(state)}")
    for k, v in statuses.items():
        print(f"  status={k}: {v} matches")
except Exception as e:
    print(f"ERROR: {e}")

# 2. Odds stream DB
print("\n=== odds_stream.db ===")
try:
    conn = sqlite3.connect(os.path.join(BASE, "data", "odds_stream.db"))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM fixture")
    print(f"Total fixtures: {c.fetchone()[0]}")
    c.execute("SELECT MAX(scraped_at) FROM fixture")
    print(f"Last scraped_at: {c.fetchone()[0]}")
    c.execute(
        "SELECT kickoff_date, COUNT(*) FROM fixture GROUP BY kickoff_date ORDER BY kickoff_date DESC LIMIT 6"
    )
    print("Fixtures by date:")
    for r in c.fetchall():
        print(f"  {r[0]}: {r[1]}")
    c.execute(
        "SELECT home_team, away_team, kickoff_date, tournament_name FROM fixture ORDER BY scraped_at DESC LIMIT 5"
    )
    print("5 most recently scraped:")
    for r in c.fetchall():
        h = (r[0] or "").encode("ascii", "replace").decode()
        a = (r[1] or "").encode("ascii", "replace").decode()
        t = (r[3] or "").encode("ascii", "replace").decode()
        print(f"  {h} vs {a} | {r[2]} | {t}")
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")

# 3. Open bets in bet_log
print("\n=== bet_log — OPEN bets ===")
try:
    conn2 = sqlite3.connect(os.path.join(BASE, "data", "bet_log.db"))
    conn2.row_factory = sqlite3.Row
    c2 = conn2.cursor()
    c2.execute("SELECT COUNT(*) as cnt FROM bet_log WHERE result='OPEN'")
    total_open = c2.fetchone()["cnt"]
    print(f"Total OPEN bets: {total_open}")
    c2.execute(
        "SELECT match_id, market_type, side, placed_at, result FROM bet_log WHERE result='OPEN' ORDER BY placed_at ASC LIMIT 10"
    )
    print("Oldest 10:")
    for r in c2.fetchall():
        mid = str(r["match_id"]).encode("ascii", "replace").decode()
        print(f"  {r['placed_at']} | {mid[:40]} | {r['market_type']} | {r['side']}")
    conn2.close()
except Exception as e:
    print(f"ERROR: {e}")

# 4. Log files
print("\n=== Server logs (last 20 lines) ===")
log_dir = os.path.join(BASE, "logs")
if os.path.exists(log_dir):
    logs = sorted([f for f in os.listdir(log_dir) if f.endswith(".log")], reverse=True)
    if logs:
        log_path = os.path.join(log_dir, logs[0])
        print(f"Log: {logs[0]}")
        with open(log_path, encoding="utf-8", errors="replace") as lf:
            lines = lf.readlines()
        for line in lines[-20:]:
            print(" ", line.rstrip().encode("ascii", "replace").decode())
    else:
        print("No log files")
else:
    print("No logs/ dir")
