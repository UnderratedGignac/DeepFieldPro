from tools.pinnacle_steam import pinnacle_steam_moves, check_pinnacle_steam

matches = [
    ("Portugal", "Uzbekistan"),
    ("England", "Ghana"),
    ("France", "Iraq"),
    ("Norway", "Senegal"),
    ("Jordan", "Algeria"),
]

for home, away in matches:
    fired, sel, move = check_pinnacle_steam(home, away, min_move_pct=2.0, window_hours=6.0)
    print(f"\n{home} vs {away}:  fired={fired}  sel={sel}  move={move:.2f}pp")
    moves = pinnacle_steam_moves(home, away, window_hours=6.0)
    meta = moves.get("__meta__", {})
    for s in ("home", "draw", "away"):
        m = moves.get(s, 0.0)
        sm = meta.get(s, {})
        ep = sm.get("earliest_prob", 0)
        lp = sm.get("latest_prob", 0)
        snaps = sm.get("snapshot_count", 0)
        print(f"  {s}: {m*100:+.3f}pp   ep={ep:.4f} -> lp={lp:.4f}   ({snaps} snaps)")
