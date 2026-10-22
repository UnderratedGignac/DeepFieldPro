import sqlite3, json, os, time, datetime

# ── Bet log ──────────────────────────────────────────────────────────────────
con = sqlite3.connect("data/bet_log.db")
rows = con.execute(
    "SELECT bet_id, match_id, bet_source, entry_odds, stake, result, pnl, placed_at "
    "FROM bet_log ORDER BY placed_at DESC"
).fetchall()
con.close()
print(f"=== BET LOG: {len(rows)} total bets ===")
for r in rows[:10]:
    print(" ", r)

# ── Dashboard state ───────────────────────────────────────────────────────────
print()
with open("data/todays_dashboard_state.json") as f:
    state = json.load(f)
print(f"=== DASHBOARD STATE: {len(state)} matches ===")
for m in state[:8]:
    sels = m.get("selections", [])
    print(f"\n  {m.get('home')} vs {m.get('away')}  [{m.get('league')}]")
    for s in sels:
        print(
            f"    {s.get('name'):20} odds={s.get('odds')}  "
            f"steam={s.get('steam_move')}%  "
            f"pin_steam={s.get('pinnacle_steam')}pp  "
            f"rec={s.get('is_recommended')}  "
            f"ev={s.get('ev_pct')}%"
        )

# ── Settings that gate bets ───────────────────────────────────────────────────
print()
with open("data/settings.json") as f:
    s = json.load(f)
print("=== ACTIVE BET GATES ===")
print(f"  steam_betting_enabled      : {s.get('steam_betting_enabled')}")
print(f"  steam_min_move_pct         : {s.get('steam_min_move_pct')}%")
print(f"  steam_flat_stake           : ${s.get('steam_flat_stake')}")
print(f"  steam_league_whitelist     : {s.get('steam_league_whitelist')}")
print(f"  require_steam_confirm      : {s.get('require_steam_confirm')}")
print(f"  sharp_steam_betting_enabled: {s.get('sharp_steam_betting_enabled')}")
print(f"  pinnacle_steam_min_move_pct: {s.get('pinnacle_steam_min_move_pct')}pp")
print(f"  ai_real_staking_enabled    : {s.get('ai_real_staking_enabled')}")
print(f"  min_ev_threshold           : {s.get('min_ev_threshold')}")
print(f"  min_confidence_pct         : {s.get('min_confidence_pct')}%")

# ── odds_history freshness ────────────────────────────────────────────────────
print()
con2 = sqlite3.connect("data/deepfield_browser_data/completed_fixtures.db")
n_odds = con2.execute("SELECT COUNT(*) FROM odds_history").fetchone()[0]
latest_odds = con2.execute("SELECT MAX(timestamp) FROM odds_history").fetchone()[0]
n_steam = con2.execute("SELECT COUNT(*) FROM steam_signals").fetchone()[0]
n_snaps = con2.execute("SELECT COUNT(*) FROM sharp_odds_history").fetchone()[0]
latest_pin = con2.execute("SELECT MAX(ts) FROM sharp_odds_history").fetchone()[0]
con2.close()
now = time.time()
stale_odds = (now - latest_odds) / 60 if latest_odds else 9999
stale_pin = (now - latest_pin) / 60 if latest_pin else 9999
print(f"=== DATA FRESHNESS ===")
print(f"  odds_history rows      : {n_odds:,}  (latest {stale_odds:.0f}m ago)")
print(f"  sharp_odds_history rows: {n_snaps:,}  (latest {stale_pin:.0f}m ago)")
print(f"  steam_signals          : {n_steam} rows")

# ── Bankroll ─────────────────────────────────────────────────────────────────
print()
con3 = sqlite3.connect("data/bankroll.db")
row = con3.execute("SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1").fetchone()
con3.close()
print(f"=== BANKROLL: ${row[0]:.2f} ===")
