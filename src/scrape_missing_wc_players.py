"""
DeepFieldPro - Missing Leagues Scraper
Scrapes the 6 valid FBref leagues that were NOT in the original global scrape:
  - ARG-Primera Division
  - BEL-Pro League
  - BRA-Brasileirao
  - ENG-Championship
  - KSA-Saudi Pro League
  - USA-MLS

Appends all WC players found to world_cup_players_match_logs_global.csv
"""
import soccerdata as sd
import pandas as pd
import unicodedata
import re
import os
import sys
import io
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_DIR   = os.path.join(os.path.dirname(__file__), '../data')
GLOBAL_CSV = os.path.join(DATA_DIR, 'world_cup_players_match_logs_global.csv')
MISSING_CSV = os.path.join(DATA_DIR, 'wc_player_name_mapping.csv')

# Leagues with their correct season format:
# - European winter leagues use '2526' (Aug 2025 - May 2026)
# - Calendar-year leagues use '2025'
LEAGUE_SEASONS = {
    'USA-MLS':              '2025',  # Messi, Busquets, Shaqiri
    'KSA-Saudi Pro League': '2025',  # Al Dawsari + Saudi squad
    'BRA-Brasileirao':      '2025',  # Brazilian domestic players
    'ARG-Primera Division': '2025',  # Argentine domestic players
    'BEL-Pro League':       '2526',  # Belgian WC players
    'ENG-Championship':     '2526',  # English 2nd tier WC players
}

# ── HELPERS ──────────────────────────────────────────────────────────────────
def normalize_name(name):
    if not isinstance(name, str): return ''
    name = name.lower().strip()
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r'[^a-z\s]', '', name)
    return re.sub(r'\s+', ' ', name).strip()

print("=" * 65)
print("DeepFieldPro - Missing 6 Leagues Scraper")
print("=" * 65)

# Load missing WC players (legal names)
mapping = pd.read_csv(MISSING_CSV)
missing_legal = mapping[mapping['fbref_name'].isna()]['legal_name'].tolist()
missing_norm  = set(normalize_name(n) for n in missing_legal)
missing_tokens_list = [set(normalize_name(n).split()) for n in missing_legal]
print(f"\nTargeting {len(missing_legal)} missing WC players")
print(f"Leagues to scrape: {MISSING_LEAGUES}")

def is_wc_player(name):
    """Multi-strategy WC player check (optimized)."""
    norm = normalize_name(name)
    if not norm: return False
    # Exact
    if norm in missing_norm: return True
    tokens = set(norm.split())
    if not tokens: return False
    for wc_toks in missing_tokens_list:
        if not wc_toks: continue
        # FBref name subset of legal name (e.g. "Lionel Messi" in "Lionel Andres Messi Cuccittini")
        if len(tokens) >= 2 and tokens.issubset(wc_toks): return True
        # Legal name subset of FBref name
        if len(wc_toks) >= 2 and wc_toks.issubset(tokens): return True
        # 2+ token overlap
        if len(tokens & wc_toks) >= 2: return True
    return False

# Load existing data (only player column to save memory)
print(f"\nLoading existing player list...")
existing_players_df = pd.read_csv(GLOBAL_CSV, usecols=['player_'])
existing_players = set(existing_players_df['player_'].dropna().str.strip().unique())
print(f"  Existing unique players: {len(existing_players):,}")
del existing_players_df  # Free memory

# Load existing game IDs for deduplication (load separately)
print(f"  Loading existing game IDs...")
existing_ids_df = pd.read_csv(GLOBAL_CSV, usecols=['game_id_'])
existing_game_ids = set(existing_ids_df['game_id_'].dropna().unique())
print(f"  Existing game IDs: {len(existing_game_ids):,}")
del existing_ids_df

all_new_frames = []
found_wc_players = {}  # player_name -> league

# ── SCRAPE EACH LEAGUE ───────────────────────────────────────────────────────
for league, season in LEAGUE_SEASONS.items():
    print(f"\n{'-'*65}")
    print(f"  Scraping: {league}")
    
    try:
        print(f"  Season format: {season}")
        fbref = sd.FBref(leagues=league, seasons=season)
        stats = fbref.read_player_match_stats(stat_type='summary')
        
        if stats is None or len(stats) == 0:
            print(f"  [EMPTY] No data returned")
            continue
        
        # Flatten MultiIndex columns
        stats = stats.reset_index()
        if hasattr(stats.columns, 'levels'):
            stats.columns = ['_'.join(filter(None, map(str, col))).strip('_') 
                             for col in stats.columns]
        
        print(f"  Raw rows: {len(stats):,} | Cols: {len(stats.columns)}")
        
        # Find player column
        player_col = next((c for c in ['player', 'Player', 'player_'] if c in stats.columns), None)
        if not player_col:
            print(f"  [WARN] No player column. Cols: {stats.columns.tolist()[:8]}")
            continue
        
        # Print sample players to verify
        sample = stats[player_col].dropna().unique()[:5]
        print(f"  Sample players: {list(sample)}")
        
        # Filter to WC players only
        stats['_is_wc'] = stats[player_col].apply(is_wc_player)
        wc_rows = stats[stats['_is_wc']].copy()
        
        if len(wc_rows) == 0:
            print(f"  No WC players matched")
            # Show what players ARE in this league
            all_p = stats[player_col].dropna().unique()
            print(f"  Total players in league: {len(all_p)}")
            # Check if any match loosely
            for p in all_p:
                norm = normalize_name(p)
                for wc_toks in missing_tokens_list:
                    if len(set(norm.split()) & wc_toks) >= 1:
                        print(f"    Possible partial match: {p}")
                        break
            continue
        
        wc_rows = wc_rows.drop(columns=['_is_wc'], errors='ignore')
        
        # Remove already-seen game IDs
        if 'game_id_' in wc_rows.columns:
            new_mask = ~wc_rows['game_id_'].isin(existing_game_ids)
            wc_rows = wc_rows[new_mask]
        
        if len(wc_rows) == 0:
            wc_found = stats[stats['_is_wc']][player_col].unique()
            print(f"  Already have all data for: {list(wc_found)}")
            continue
        
        # Tag with league
        wc_rows['league_'] = league
        
        # Record found players
        for p in wc_rows[player_col].unique():
            found_wc_players[p] = league
        
        all_new_frames.append(wc_rows)
        print(f"  [SUCCESS] Found {wc_rows[player_col].nunique()} WC players | {len(wc_rows):,} new rows")
        for p in wc_rows[player_col].unique():
            print(f"    + {p}")
        
        time.sleep(6)  # FBref rate limit
        
    except Exception as e:
        print(f"  [ERROR] {league}: {e}")
        time.sleep(5)
        continue

# ── APPEND TO GLOBAL CSV ─────────────────────────────────────────────────────
print(f"\n{'='*65}")
print("SCRAPE RESULTS")
print(f"  WC players newly found: {len(found_wc_players)}")

if all_new_frames:
    new_data = pd.concat(all_new_frames, ignore_index=True)
    print(f"  New rows total: {len(new_data):,}")
    
    # Load existing full CSV now for appending
    print("\n  Loading existing CSV for merge...")
    existing_full = pd.read_csv(GLOBAL_CSV)
    
    # Align columns
    for col in existing_full.columns:
        if col not in new_data.columns:
            new_data[col] = None
    new_data = new_data[[c for c in existing_full.columns if c in new_data.columns]]
    
    combined = pd.concat([existing_full, new_data], ignore_index=True)
    
    # Dedup on game_id + player
    if 'game_id_' in combined.columns and 'player_' in combined.columns:
        before = len(combined)
        combined = combined.drop_duplicates(subset=['game_id_', 'player_'], keep='first')
        print(f"  Deduped: {before - len(combined)} duplicates removed")
    
    combined.to_csv(GLOBAL_CSV, index=False)
    print(f"\n  UPDATED: {GLOBAL_CSV}")
    print(f"  Total rows: {len(combined):,} (was {len(existing_full):,})")
    
    print(f"\nNewly added WC players:")
    for p, lg in sorted(found_wc_players.items()):
        print(f"  + [{lg}] {p}")
else:
    print("\n  No new WC player data found.")
    print("  These players may play in leagues FBref doesn't cover")
    print("  (Iranian, Croatian, Danish, Tunisian, J-League, K-League, etc.)")

print("\nDone!")
