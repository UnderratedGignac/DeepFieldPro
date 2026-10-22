"""Check fixture ID alignment between dashboard and odds_history."""
import sqlite3, json, os

with open("data/todays_dashboard_state.json") as f:
    state = json.load(f)

con = sqlite3.connect("data/deepfield_browser_data/completed_fixtures.db")

# Check WC fixture IDs in dashboard vs odds_history
wc_matches = [m for m in state if "World Cup" in (m.get("league") or "")]
print(f"WC matches in dashboard: {len(wc_matches)}")
for m in wc_matches[:10]:
    fid = str(m.get("fixture_id", ""))
    count = con.execute(
        "SELECT COUNT(*) FROM odds_history WHERE fixture_id=?", (fid,)
    ).fetchone()[0]
    print(f"  {m['match']}  fid={fid}  odds_history={count} rows")

print()
print("Sample fixture IDs in odds_history (most recent):")
rows = con.execute(
    "SELECT DISTINCT fixture_id FROM odds_history ORDER BY rowid DESC LIMIT 10"
).fetchall()
for r in rows:
    print(" ", r[0])

con.close()

# Check odds_stream.db for WC fixtures
if os.path.exists("data/odds_stream.db"):
    con2 = sqlite3.connect("data/odds_stream.db")
    tables = con2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("\nodds_stream.db tables:", [t[0] for t in tables])
    try:
        wc = con2.execute(
            "SELECT fixture_id, home_team, away_team, tournament_name "
            "FROM fixture WHERE tournament_name LIKE '%World Cup%' LIMIT 10"
        ).fetchall()
        print("WC in odds_stream.db fixture table:")
        for r in wc:
            print(" ", r)
    except Exception as e:
        print("Error:", e)
    con2.close()
else:
    print("odds_stream.db not found")
