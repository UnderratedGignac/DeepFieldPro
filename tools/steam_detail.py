"""Show exact price movements for all whitelisted-league matches."""
import sqlite3, json

with open("data/todays_dashboard_state.json") as f:
    state = json.load(f)

con = sqlite3.connect("data/deepfield_browser_data/completed_fixtures.db")

STEAM_WL = [
    "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
    "eredivisie", "primeira liga", "championship", "scottish premiership",
    "champions league", "europa league", "fifa world cup", "world cup",
]

def devig(h, d, a):
    total = 1/h + 1/d + 1/a if h and d and a else None
    if not total:
        return None, None, None
    return (1/h)/total, (1/d)/total, (1/a)/total

print(f"{'Match':<40} {'League':<20} {'Sel':<8} {'Earliest':>8} {'Latest':>8} {'Move':>8} {'Snaps':>6}")
print("-" * 105)

for m in state:
    league = (m.get("league") or "")
    league_lower = league.lower()
    if not any(w in league_lower for w in STEAM_WL):
        continue

    fid = str(m.get("fixture_id", ""))
    match = m.get("match", "?")

    for sel in ("Home (1)", "Draw (X)", "Away (2)"):
        rows = con.execute(
            "SELECT odds, timestamp FROM odds_history "
            "WHERE fixture_id=? AND market='1X2' AND selection=? "
            "ORDER BY timestamp ASC",
            (fid, sel),
        ).fetchall()

        if not rows:
            continue

        unique_ts = set(r[1] for r in rows)
        if len(unique_ts) < 2:
            continue

        e_odds = rows[0][0]
        l_odds = rows[-1][0]

        if e_odds <= 0 or l_odds <= 0:
            continue

        e_prob = 1.0 / e_odds
        l_prob = 1.0 / l_odds
        move = (l_prob - e_prob) * 100

        label = "home" if "Home" in sel else "draw" if "Draw" in sel else "away"
        flag = " <<< STEAM" if abs(move) >= 5.0 else (" (close)" if abs(move) >= 2.0 else "")
        print(
            f"  {match[:38]:<38} {league[:18]:<18} {label:<8} "
            f"{e_odds:>8.3f} {l_odds:>8.3f} {move:>+7.2f}pp {len(unique_ts):>6}{flag}"
        )

con.close()
