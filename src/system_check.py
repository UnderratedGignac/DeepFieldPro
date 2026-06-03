"""
system_check.py - Full system health audit for DeepFieldPro
"""
import sqlite3
import json
import os
import sys
import importlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

print("=" * 60)
print("DEEPFIELDPRO SYSTEM HEALTH CHECK")
print("=" * 60)

# ── 1. DATABASE ────────────────────────────────────────────────
print("\n[1] DATABASE")
db_path = os.path.join(BASE, "data", "odds_stream.db")
if not os.path.exists(db_path):
    print("  ERROR: odds_stream.db not found")
else:
    db = sqlite3.connect(db_path)
    fixtures = db.execute("SELECT COUNT(*) FROM fixture").fetchone()[0]
    markets = db.execute("SELECT COUNT(*) FROM market").fetchone()[0]
    print(f"  fixtures: {fixtures}, markets: {markets}")
    rows = db.execute(
        "SELECT fixture_id, home_team, away_team, kickoff_time, league_id FROM fixture WHERE fixture_id != 'fix_001' ORDER BY scraped_at DESC LIMIT 20"
    ).fetchall()
    print(f"  Latest fixtures ({len(rows)}):")
    for r in rows:
        print(f"    [{r[0]}] {r[1]} vs {r[2]} | KO: {r[3]} | League: {r[4]}")

    # Check markets per fixture
    mkt_per_fix = db.execute(
        "SELECT fixture_id, COUNT(*) FROM market GROUP BY fixture_id LIMIT 10"
    ).fetchall()
    print("  Markets per fixture (sample):")
    for m in mkt_per_fix:
        print(f"    {m[0]}: {m[1]} markets")

# ── 2. MODEL FILES ─────────────────────────────────────────────
print("\n[2] MODEL FILES")
models_path = os.path.join(BASE, "models")
if os.path.exists(models_path):
    model_files = os.listdir(models_path)
    for f in model_files:
        size = os.path.getsize(os.path.join(models_path, f))
        print(f"  {f}: {size//1024}KB")
else:
    print("  ERROR: models/ directory not found")

# ── 3. API RESPONSE FILE ───────────────────────────────────────
print("\n[3] API RESPONSES (betarabia)")
api_path = os.path.join(BASE, "data", "betarabia_api_responses.json")
if os.path.exists(api_path):
    data = json.load(open(api_path, encoding="utf-8"))
    print(f"  {len(data)} captured API calls")
    event_urls = [x.get("url", "") for x in data if "events" in x.get("url", "") or "prematch" in x.get("url", "")]
    odds_urls = [x.get("url", "") for x in data if "odds" in x.get("url", "")]
    print(f"  Event/prematch URLs: {len(event_urls)}")
    print(f"  Odds URLs: {len(odds_urls)}")
    for u in event_urls[:3]:
        print(f"    - {u}")
    for u in odds_urls[:3]:
        print(f"    - {u}")
else:
    print("  No betarabia_api_responses.json found")

# ── 4. PYTHON MODULE IMPORTS ───────────────────────────────────
print("\n[4] MODULE IMPORTS")
modules_to_check = [
    "src.single_bet_predictor",
    "src.parlay_builder",
    "src.pricing_engine",
    "src.kelly_calculator",
    "src.utils",
]
for mod in modules_to_check:
    try:
        importlib.import_module(mod)
        print(f"  OK  {mod}")
    except Exception as e:
        print(f"  ERR {mod}: {e}")

# ── 5. OUTPUT FILES ────────────────────────────────────────────
print("\n[5] OUTPUT FILES")
data_dir = os.path.join(BASE, "data")
output_files = [f for f in os.listdir(data_dir) if "BETS" in f or "predictions" in f.lower()]
for f in sorted(output_files):
    fpath = os.path.join(data_dir, f)
    size = os.path.getsize(fpath)
    mtime = os.path.getmtime(fpath)
    import datetime
    mt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    print(f"  {f}: {size//1024}KB  (last modified: {mt})")

print("\n" + "=" * 60)
print("HEALTH CHECK COMPLETE")
print("=" * 60)
