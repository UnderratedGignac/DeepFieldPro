"""
DeepFieldPro - Missing WC Player Scraper
Targets leagues NOT covered by the original global scraper:
- MLS, Saudi Pro League, Iranian Pro League, Croatian HNL,
  Swiss Super League, Danish Superliga, Tunisian League,
  J1 League, K League, Qatar Stars League
  
Appends results to existing world_cup_players_match_logs_global.csv
"""
import soccerdata as sd
import pandas as pd
import numpy as np
import unicodedata
import re
import os
import time
import sys

print("=" * 65)
print("DeepFieldPro - Missing WC Player Scraper")
print("=" * 65)

DATA_DIR = os.path.join(os.path.dirname(__file__), '../data')
GLOBAL_CSV  = os.path.join(DATA_DIR, 'world_cup_players_match_logs_global.csv')
WC_CSV      = os.path.join(DATA_DIR, 'worldcup_players.csv')
MISSING_CSV = os.path.join(DATA_DIR, 'wc_player_name_mapping.csv')
OUTPUT_CSV  = os.path.join(DATA_DIR, 'world_cup_players_match_logs_global.csv')

# ── 1. LOAD MISSING PLAYER LIST ─────────────────────────────────────────────
mapping = pd.read_csv(MISSING_CSV)
unmatched = mapping[mapping['fbref_name'].isna()]['legal_name'].tolist()
print(f"\nMissing players to find: {len(unmatched)}")

def normalize_name(name):
    if not isinstance(name, str): return ''
    name = name.lower().strip()
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r'[^a-z\s]', '', name)
    return re.sub(r'\s+', ' ', name).strip()

# Build normalized lookup for fast matching
missing_norm = set(normalize_name(n) for n in unmatched)

# Also build token-based index for fuzzy matching
missing_tokens = [set(normalize_name(n).split()) for n in unmatched]

def is_wc_player(name):
    """Fast check: is this player name a missing WC player?"""
    norm = normalize_name(name)
    if norm in missing_norm:
        return True
    tokens = set(norm.split())
    for wc_tok in missing_tokens:
        if len(tokens) >= 1 and len(wc_tok) >= 1:
            # Check subset: all FBref tokens in legal name tokens
            if tokens.issubset(wc_tok) and len(tokens) >= 2:
                return True
            if wc_tok.issubset(tokens) and len(wc_tok) >= 2:
                return True
            if len(tokens & wc_tok) >= 2:
                return True
    return False

# ── 2. DEFINE TARGET LEAGUES ─────────────────────────────────────────────────
# These are the leagues NOT covered by the original scraper
# soccerdata FBref league codes:
TARGET_LEAGUES = [
    # League Name                    | Why needed
    "USA-Major League Soccer",       # Messi (Inter Miami), Busquets, Shaqiri
    "SAU-Saudi Pro League",          # Al Dawsari, Saudi players, Ziyech (Al-Qadsiah)
    "IRN-Persian Gulf Pro League",   # Taremi, Azmoun
    "HRV-HNL",                       # Brozovic (Hajduk Split), Livaja, Orsic
    "CHE-Super League",              # Embolo, Shaqiri
    "DNK-Superliga",                 # Andreas Cornelius
    "TUN-Ligue Professionnelle 1",   # Msakni, Jebali
    "JPN-J1 League",                 # Yoshida, Maeda, Asano
    "KOR-K League 1",                # Korean players
    "QAT-Stars League",              # Al Moez Ali (Al Duhail), Qatar WC players
    "BEL-First Division A",          # Dries Mertens (Galatasaray but also Belgium players)
    "SRB-Super Liga",                # Mitrovic (Al-Hilal but also Serbian league)
    "SCO-Premiership",               # Bale (played Cardiff) - extended
    "GRE-Super League",              # Extra Balkan players
    "CZE-Fortuna Liga",              # Czech players
    "SVK-Fortuna Liga",              # Slovak players  
    "ROU-SuperLiga",                 # Romanian players
    "AUT-Bundesliga",                # Austrian players
    "UKR-Premier League",            # Ukrainian players
    "RUS-Premier League",            # Russian-based players (if available)
]

SEASON = "2526"  # 2025-26 season

# ── 3. LOAD EXISTING DATA TO AVOID DUPLICATES ────────────────────────────────
print("\n[3] Loading existing global match logs...")
existing_df = pd.read_csv(GLOBAL_CSV)
existing_match_ids = set(existing_df['game_id_'].dropna().unique())
existing_players = set(existing_df['player_'].dropna().str.strip())
print(f"  Existing rows: {len(existing_df):,}")
print(f"  Existing match IDs: {len(existing_match_ids):,}")
print(f"  Existing players: {len(existing_players):,}")

# ── 4. SCRAPE MISSING LEAGUES ────────────────────────────────────────────────
all_new_frames = []
found_wc_players = set()
total_new_rows = 0

for league in TARGET_LEAGUES:
    print(f"\n{'─'*60}")
    print(f"  Scraping: {league}")
    
    try:
        fbref = sd.FBref(leagues=league, seasons=SEASON)
        
        # Get player match stats
        stats = fbref.read_player_match_stats(stat_type="summary")
        
        if stats is None or len(stats) == 0:
            print(f"  [SKIP] No data returned for {league}")
            continue
        
        # Flatten MultiIndex columns if present
        if hasattr(stats.columns, 'levels'):
            stats.columns = ['_'.join(filter(None, map(str, col))).strip('_') 
                             for col in stats.columns]
        
        stats = stats.reset_index()
        print(f"  Raw rows: {len(stats):,}")
        
        # Identify player column
        player_col = None
        for col in ['player', 'Player', 'player_']:
            if col in stats.columns:
                player_col = col
                break
        
        if not player_col:
            print(f"  [WARN] No player column found. Columns: {stats.columns.tolist()[:10]}")
            continue
        
        # Filter to WC players only
        stats['_is_wc'] = stats[player_col].apply(is_wc_player)
        wc_rows = stats[stats['_is_wc']].copy()
        
        if len(wc_rows) == 0:
            print(f"  No WC players found in {league}")
            continue
        
        wc_found = wc_rows[player_col].unique()
        for p in wc_found:
            found_wc_players.add(p)
        
        # Remove duplicates vs existing data
        if 'game_id_' in wc_rows.columns:
            new_rows = wc_rows[~wc_rows['game_id_'].isin(existing_match_ids)]
        elif 'game_' in wc_rows.columns:
            # Use game + player as dedup key
            existing_keys = set(zip(existing_df.get('game_', pd.Series([])), 
                                    existing_df.get('player_', pd.Series([]))))
            new_rows = wc_rows  # Keep all, merge will dedup later
        else:
            new_rows = wc_rows
        
        # Add source league metadata
        new_rows = new_rows.drop(columns=['_is_wc'], errors='ignore')
        
        if len(new_rows) > 0:
            all_new_frames.append(new_rows)
            total_new_rows += len(new_rows)
            print(f"  ✓ Found {len(wc_found)} WC players | {len(new_rows):,} new rows")
            for p in wc_found:
                print(f"      - {p}")
        else:
            print(f"  Already have all data for {len(wc_found)} WC players in {league}")
        
        # FBref rate limit respect
        time.sleep(5)
        
    except Exception as e:
        err = str(e)
        if 'CAPTCHA' in err or 'IP block' in err or 'timeout' in err.lower():
            print(f"  [BLOCKED] Rate limited on {league}. Sleeping 60s...")
            time.sleep(60)
        elif 'not found' in err.lower() or 'invalid' in err.lower():
            print(f"  [SKIP] League {league} not available: {e}")
        else:
            print(f"  [ERROR] {league}: {e}")
        time.sleep(3)
        continue

# ── 5. APPEND TO GLOBAL CSV ─────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"SCRAPE COMPLETE")
print(f"  New WC players found: {len(found_wc_players)}")
print(f"  Total new rows collected: {total_new_rows:,}")

if all_new_frames:
    new_data = pd.concat(all_new_frames, ignore_index=True)
    
    # Combine with existing
    combined = pd.concat([existing_df, new_data], ignore_index=True)
    
    # Deduplicate
    if 'game_id_' in combined.columns and 'player_' in combined.columns:
        combined = combined.drop_duplicates(
            subset=['game_id_', 'player_'], keep='first'
        )
    
    combined.to_csv(OUTPUT_CSV, index=False)
    print(f"\n  Updated CSV: {OUTPUT_CSV}")
    print(f"  Total rows now: {len(combined):,}")
    print(f"  New WC players added: {len(found_wc_players)}")
    
    for p in sorted(found_wc_players):
        print(f"    ✓ {p}")
else:
    print("\n  No new data collected.")
    print("  All missing players play in leagues not on FBref, or were rate-limited.")

print(f"\nNew WC players found: {', '.join(sorted(found_wc_players)) if found_wc_players else 'None'}")
print("Done!")
