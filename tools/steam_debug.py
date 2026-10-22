"""Diagnose why STEAM bets are not firing."""
import sqlite3, json, time

with open("data/todays_dashboard_state.json") as f:
    state = json.load(f)

con = sqlite3.connect("data/deepfield_browser_data/completed_fixtures.db")

STEAM_WL = [
    "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
    "eredivisie", "primeira liga", "championship", "scottish premiership",
    "champions league", "europa league", "fifa world cup", "world cup",
]

STEAM_MIN_MOVE = 0.05  # 5% as set in settings.json

print(f"Dashboard matches: {len(state)}")
print(f"Steam whitelist: {STEAM_WL[:4]}...")
print(f"Steam min move: {STEAM_MIN_MOVE*100:.0f}%")
print()

wl_matches = []
for m in state:
    league_lower = (m.get("league") or "").lower()
    if any(w in league_lower for w in STEAM_WL):
        wl_matches.append(m)

print(f"Whitelisted matches: {len(wl_matches)}")
print()

no_odds = 0
few_snaps = 0
no_move = 0
move_too_small = 0
eligible = 0

for m in wl_matches:
    fid = str(m.get("fixture_id", ""))
    match = m.get("match", "?")
    league = m.get("league", "?")

    rows = con.execute(
        "SELECT selection, COUNT(*) snaps, COUNT(DISTINCT timestamp) distinct_ts "
        "FROM odds_history WHERE fixture_id=? AND market='1X2' GROUP BY selection",
        (fid,),
    ).fetchall()

    if not rows:
        no_odds += 1
        print(f"  [NO ODDS] {match} (fid={fid})")
        continue

    for sel, snaps, distinct_ts in rows:
        if distinct_ts < 2:
            few_snaps += 1
            continue

        # Fetch earliest and latest odds
        e_odds = con.execute(
            "SELECT odds FROM odds_history WHERE fixture_id=? AND market='1X2' AND selection=? "
            "ORDER BY timestamp ASC LIMIT 1", (fid, sel)
        ).fetchone()
        l_odds = con.execute(
            "SELECT odds FROM odds_history WHERE fixture_id=? AND market='1X2' AND selection=? "
            "ORDER BY timestamp DESC LIMIT 1", (fid, sel)
        ).fetchone()

        if not e_odds or not l_odds:
            continue

        # Simple odds move (not de-vigged — for diagnosis only)
        if e_odds[0] <= 0 or l_odds[0] <= 0:
            continue

        e_prob = 1.0 / e_odds[0]
        l_prob = 1.0 / l_odds[0]
        raw_move = l_prob - e_prob  # positive = market moved toward this team

        if abs(raw_move) < 0.001:
            no_move += 1
            continue

        if abs(raw_move) < STEAM_MIN_MOVE:
            move_too_small += 1
            if abs(raw_move) > 0.02:  # show anything >= 2%
                print(
                    f"  [CLOSE] {match} [{league}] {sel}: move={raw_move*100:+.2f}pp "
                    f"(need {STEAM_MIN_MOVE*100:.0f}%,  {distinct_ts} snaps)"
                )
            continue

        eligible += 1
        print(
            f"  [STEAM!] {match} [{league}] {sel}: move={raw_move*100:+.2f}pp "
            f"({distinct_ts} snaps, e={e_odds[0]:.2f}->l={l_odds[0]:.2f})"
        )

print()
print(f"Summary:")
print(f"  No odds in history   : {no_odds}")
print(f"  Only 1 snapshot      : {few_snaps}")
print(f"  No move detected     : {no_move}")
print(f"  Move < {STEAM_MIN_MOVE*100:.0f}% (close)  : {move_too_small}")
print(f"  STEAM eligible       : {eligible}")

# Also: how many selections total across whitelisted matches in odds_history
n = con.execute(
    "SELECT COUNT(DISTINCT fixture_id) FROM odds_history WHERE market='1X2'"
).fetchone()[0]
print(f"\n  Distinct fixtures in odds_history (1X2): {n}")

# Latest timestamp
latest = con.execute("SELECT MAX(timestamp) FROM odds_history").fetchone()[0]
print(f"  Latest odds_history entry: {latest}")

con.close()
