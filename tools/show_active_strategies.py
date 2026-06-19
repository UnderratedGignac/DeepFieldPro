import json
s = json.load(open("data/settings.json"))

print("=== WHAT PLACES BETS (after cleanup) ===")
steam_on = s.get("steam_betting_enabled", True)
sharp_on = s.get("sharp_betting_enabled", True)
sharpv_on = s.get("sharp_value_enabled", True)

print(f"  STEAM bets:    {'ON ' if steam_on else 'OFF'}  | flat_stake=${s.get('steam_flat_stake')} | min_move={s.get('steam_min_move_pct')}% | Pinnacle-only={s.get('steam_covered_only')}")
print(f"  SHARP bets:    {'ON ' if sharp_on else 'OFF'}  | removed - was losing -41%")
print(f"  SHARPV bets:   {'ON ' if sharpv_on else 'OFF'}  | removed - was losing -54%")
print(f"  AI model bets: zero-stake tracking only (ai_real_staking_enabled=False)")

print()
print("=== MARKET FILTER ===")
print(f"  allowed: {s.get('allowed_markets')}  (corners/O/U/BTTS/cards blocked)")
print(f"  draws:   excluded={s.get('exclude_draws')}")

print()
print("=== EXPECTED BET FLOW ===")
print("  Only STEAM bets fire real (paper) stakes going forward.")
print("  STEAM: Betarabia 1X2 line moves >=5% toward a side AND Pinnacle also covers the match.")
print("  When STEAM fires: $25 paper flat stake, deduped per fixture/market/selection.")
