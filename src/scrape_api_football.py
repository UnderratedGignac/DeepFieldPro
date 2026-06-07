"""
DeepFieldPro - Bulletproof API-Football Scraper
1. Downloads all 830 World Cup players from API-Football (42 paginated requests).
2. Maps their API ID to our missing players list locally.
3. Fetches their 2024/2025 match logs/stats (1 request per missing player).
"""
import requests
import pandas as pd
import unicodedata
import re
import os
import sys
import io
import time
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

DATA_DIR    = os.path.join(os.path.dirname(__file__), '../data')
GLOBAL_CSV  = os.path.join(DATA_DIR, 'world_cup_players_match_logs_global.csv')
MISSING_CSV = os.path.join(DATA_DIR, 'wc_player_name_mapping.csv')
WC_PLAYERS_JSON = os.path.join(DATA_DIR, 'api_wc_players_2022.json')
STATS_PROGRESS  = os.path.join(DATA_DIR, 'api_stats_progress.json')

API_KEY = '4ae9f07e1ae1f775050015c50037a71d'
API_BASE = 'https://v3.football.api-sports.io'
HEADERS = {'x-apisports-key': API_KEY}

print("=" * 65)
print("DeepFieldPro - API-Football Scraper (Optimized)")
print("=" * 65)

def normalize_name(name):
    if not isinstance(name, str): return ''
    name = name.lower().strip()
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r'[^a-z\s]', '', name)
    return re.sub(r'\s+', ' ', name).strip()

# ── 1. FETCH ALL WORLD CUP PLAYERS (LEAGUE 1, SEASON 2022) ───────────────────
wc_api_players = []
if os.path.exists(WC_PLAYERS_JSON):
    with open(WC_PLAYERS_JSON) as f:
        wc_api_players = json.load(f)
    print(f"[1] Loaded {len(wc_api_players)} WC players from cache.")
else:
    print("[1] Downloading WC 2022 players (42 pages, takes ~4 mins)...")
    for page in range(1, 43):
        print(f"  Fetching page {page}/42...")
        r = requests.get(f'{API_BASE}/players', headers=HEADERS, 
                         params={'league': 1, 'season': 2022, 'page': page})
        time.sleep(6.1) # 10 req/min
        
        if r.status_code == 200:
            data = r.json()
            results = data.get('response', [])
            for res in results:
                p = res.get('player', {})
                wc_api_players.append({
                    'id': p.get('id'),
                    'name': p.get('name'),
                    'firstname': p.get('firstname'),
                    'lastname': p.get('lastname')
                })
        else:
            print(f"  ERROR on page {page}: {r.status_code}")
    
    with open(WC_PLAYERS_JSON, 'w') as f:
        json.dump(wc_api_players, f)
    print(f"  Saved {len(wc_api_players)} players to cache.")

# ── 2. MATCH MISSING PLAYERS TO API IDs ───────────────────────────────────────
print("\n[2] Mapping missing players to API IDs...")
mapping = pd.read_csv(MISSING_CSV)
missing = mapping[mapping['fbref_name'].isna()]['legal_name'].tolist()

# Prepare API names for matching
api_lookup = []
for p in wc_api_players:
    full_api = f"{p.get('firstname', '')} {p.get('lastname', '')}"
    api_lookup.append({
        'id': p['id'],
        'name': p['name'],
        'norm': normalize_name(full_api),
        'toks': set(normalize_name(full_api).split())
    })

matched_ids = {} # legal_name -> id
for missing_name in missing:
    norm_m = normalize_name(missing_name)
    toks_m = set(norm_m.split())
    
    best_match = None
    for p in api_lookup:
        # Check subset
        if len(toks_m & p['toks']) >= 2:
            best_match = p
            break
        # Sometimes API has just last name or short name
        if p['toks'].issubset(toks_m) and len(p['toks']) >= 1:
            best_match = p
            break
            
    if best_match:
        matched_ids[missing_name] = best_match['id']

print(f"  Mapped {len(matched_ids)} out of {len(missing)} missing players!")

# ── 3. DOWNLOAD 2024 STATS ───────────────────────────────────────────────────
print("\n[3] Downloading 2024 season stats...")
done_stats = {}
if os.path.exists(STATS_PROGRESS):
    with open(STATS_PROGRESS) as f:
        done_stats = json.load(f)
    print(f"  Resuming from {len(done_stats)} processed players.")

all_new_rows = []
total_to_fetch = len(matched_ids)
fetched = 0

for legal_name, api_id in matched_ids.items():
    if legal_name in done_stats:
        fetched += 1
        continue
        
    print(f"  [{fetched+1}/{total_to_fetch}] Fetching stats for {legal_name} (API ID: {api_id})")
    
    r = requests.get(f'{API_BASE}/players', headers=HEADERS, 
                     params={'id': api_id, 'season': 2024})
    time.sleep(6.1) # 10 req/min limit
    
    if r.status_code == 200:
        data = r.json()
        results = data.get('response', [])
        
        player_rows = []
        if results:
            entry = results[0]
            player_info = entry.get('player', {})
            player_name = player_info.get('name', legal_name)
            
            for stat in entry.get('statistics', []):
                games = stat.get('games', {})
                goals = stat.get('goals', {})
                shots = stat.get('shots', {})
                cards = stat.get('cards', {})
                
                appearances = games.get('appearences', 0) or 0
                if appearances == 0:
                    continue
                    
                player_rows.append({
                    'Player':   player_name,
                    'player_':  legal_name, # Standardize to legal name for feature matrix
                    'Nation':   player_info.get('nationality', ''),
                    'Pos':      games.get('position', ''),
                    'Squad':    stat.get('team', {}).get('name', ''),
                    'Comp':     stat.get('league', {}).get('name', ''),
                    'league_':  stat.get('league', {}).get('name', ''),
                    'Min':      games.get('minutes', 0) or 0,
                    'Gls':      goals.get('total', 0) or 0,
                    'Ast':      goals.get('assists', 0) or 0,
                    'Sh':       shots.get('total', 0) or 0,
                    'SoT':      shots.get('on', 0) or 0,
                    'CrdY':     cards.get('yellow', 0) or 0,
                    'CrdR':     cards.get('red', 0) or 0,
                    'season_':  '2024',
                    'source':   'api-football',
                    'Date':     '2024-07-01',
                    'Opponent': 'Season Aggregate',
                    'game_id_': f"api_{api_id}_{stat.get('league',{}).get('id')}_2024",
                })
        
        if player_rows:
            all_new_rows.extend(player_rows)
            done_stats[legal_name] = {'status': 'found', 'rows': len(player_rows)}
            print(f"    ✓ Found {len(player_rows)} stat rows")
        else:
            done_stats[legal_name] = {'status': 'no_stats'}
            print("    ✗ No stats in 2024")
    else:
        print(f"    ERROR: API returned {r.status_code}")
        done_stats[legal_name] = {'status': 'error', 'code': r.status_code}
        
    with open(STATS_PROGRESS, 'w') as f:
        json.dump(done_stats, f)
        
    fetched += 1

# ── 4. APPEND TO GLOBAL CSV ──────────────────────────────────────────────────
print(f"\n{'='*65}")
print("SCRAPE COMPLETE")
print(f"  New stat rows: {len(all_new_rows)}")

if all_new_rows:
    new_df = pd.DataFrame(all_new_rows)
    existing = pd.read_csv(GLOBAL_CSV)
    
    for col in existing.columns:
        if col not in new_df.columns:
            new_df[col] = None
    new_df = new_df[[c for c in existing.columns if c in new_df.columns]]
    
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=['game_id_', 'player_'], keep='first')
    
    combined.to_csv(GLOBAL_CSV, index=False)
    print(f"  SAVED: {GLOBAL_CSV}")
    print(f"  Total rows: {len(combined):,}")
else:
    print("  No new data to save.")
print("\nDone!")
