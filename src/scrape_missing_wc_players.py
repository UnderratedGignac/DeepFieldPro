"""
DeepFieldPro - Direct FBref Player Match Log Scraper
Scrapes match logs directly from individual FBref player pages.
Bypasses soccerdata league restrictions entirely.

Strategy:
1. Search FBref for each missing WC player by name
2. Find their player page URL
3. Scrape their 2025-26 match logs
4. Append to global CSV
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os
import io
import sys
import json
import unicodedata
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_DIR    = os.path.join(os.path.dirname(__file__), '../data')
GLOBAL_CSV  = os.path.join(DATA_DIR, 'world_cup_players_match_logs_global.csv')
MISSING_CSV = os.path.join(DATA_DIR, 'wc_player_name_mapping.csv')
PROGRESS_FILE = os.path.join(DATA_DIR, 'fbref_direct_scrape_progress.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://fbref.com/',
}

SEASON_ID = "2025-2026"  # URL format

print("=" * 65)
print("DeepFieldPro - Direct FBref Player Scraper")
print("=" * 65)

# ── 1. LOAD MISSING PLAYERS ──────────────────────────────────────────────────
mapping = pd.read_csv(MISSING_CSV)
missing = mapping[mapping['fbref_name'].isna()]['legal_name'].tolist()
print(f"\nTargeting {len(missing)} missing WC players")

# Load progress to allow resuming
scraped_done = {}
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE) as f:
        scraped_done = json.load(f)
    print(f"Resuming from previous run ({len(scraped_done)} already done)")

# Load existing data
existing_df = pd.read_csv(GLOBAL_CSV)
print(f"Existing rows: {len(existing_df):,}")

def normalize_name(name):
    if not isinstance(name, str): return ''
    n = name.lower().strip()
    n = unicodedata.normalize('NFKD', n)
    n = ''.join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r'[^a-z\s]', '', n)
    return re.sub(r'\s+', ' ', n).strip()

def search_fbref_player(name):
    """Search FBref for a player and return their player page URL."""
    # FBref search URL
    search_url = "https://fbref.com/search/search.fcgi"
    params = {"search": name, "pid": "search"}
    
    try:
        r = requests.get(search_url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Check for direct redirect to player page
        if '/players/' in r.url and r.url != search_url:
            return r.url
        
        # Look for search results
        results = soup.find_all('div', {'class': 'search-item-name'})
        for result in results:
            link = result.find('a', href=True)
            if link and '/players/' in link['href']:
                return "https://fbref.com" + link['href']
        
        # Try parsing strong links
        for a in soup.find_all('a', href=True):
            if '/players/' in a['href'] and re.match(r'/en/players/[a-f0-9]{8}/', a['href']):
                return "https://fbref.com" + a['href']
                
        return None
    except Exception as e:
        print(f"    Search error: {e}")
        return None

def get_match_logs_url(player_url):
    """Get the match logs page URL for a player."""
    # Convert player page URL to match logs URL
    # e.g.: /en/players/d70ce98e/Lionel-Messi
    # Match logs: /en/players/d70ce98e/matchlogs/2025-2026/summary/Lionel-Messi-Match-Logs
    
    # Extract player ID and name slug from URL
    match = re.search(r'/players/([a-f0-9]{8})/([^/]+)$', player_url.rstrip('/'))
    if not match:
        return None
    
    player_id = match.group(1)
    name_slug = match.group(2)
    
    return f"https://fbref.com/en/players/{player_id}/matchlogs/{SEASON_ID}/summary/{name_slug}-Match-Logs"

def scrape_match_log_page(logs_url, player_name):
    """Scrape the match log table from FBref player page."""
    try:
        r = requests.get(logs_url, headers=HEADERS, timeout=30)
        
        if r.status_code == 429:
            return None, "rate_limited"
        if r.status_code == 404:
            return None, "not_found"
        r.raise_for_status()
        
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Find the match log table
        table = soup.find('table', {'id': re.compile(r'matchlogs_')})
        if not table:
            # Try any table with stats
            tables = soup.find_all('table')
            if not tables:
                return None, "no_table"
            table = tables[0]
        
        # Parse with pandas
        dfs = pd.read_html(str(table))
        if not dfs:
            return None, "no_data"
        
        df = dfs[0]
        
        # Flatten MultiIndex columns
        if hasattr(df.columns, 'levels'):
            df.columns = ['_'.join(filter(None, map(str, col))).strip('_') 
                         for col in df.columns]
        
        # Add player name
        df['player_'] = player_name
        
        # Remove rows that are sub-headers (FBref repeats headers)
        if 'Date' in df.columns:
            df = df[df['Date'].notna()]
            df = df[~df['Date'].str.contains('Date', na=True)]
            df = df[~df['Date'].str.contains('Matches', na=True)]
        
        # Filter to 2025-26 season
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df = df[df['Date'] >= '2025-07-01']
            df = df[df['Date'].notna()]
        
        return df, "ok"
        
    except Exception as e:
        return None, str(e)[:80]

# ── 2. SCRAPE EACH MISSING PLAYER ────────────────────────────────────────────
all_new_frames = []
found_players = []
failed_players = []

for i, player_name in enumerate(missing):
    if player_name in scraped_done:
        status = scraped_done[player_name]
        if status == "found":
            print(f"  [{i+1}/{len(missing)}] {player_name[:40]:40s} [already found]")
        continue
    
    print(f"\n  [{i+1}/{len(missing)}] Searching: {player_name[:50]}")
    
    # Step 1: Search for player
    player_url = search_fbref_player(player_name)
    time.sleep(4)  # Rate limit
    
    if not player_url:
        # Try with just the last 2 words of the name
        name_parts = player_name.split()
        short_name = ' '.join(name_parts[-2:]) if len(name_parts) >= 2 else player_name
        print(f"    Retrying with short name: {short_name}")
        player_url = search_fbref_player(short_name)
        time.sleep(4)
    
    if not player_url:
        print(f"    [NOT FOUND] Could not find player page")
        scraped_done[player_name] = "not_found"
        failed_players.append(player_name)
        continue
    
    print(f"    Found: {player_url}")
    
    # Step 2: Get match logs URL
    logs_url = get_match_logs_url(player_url)
    if not logs_url:
        print(f"    [ERROR] Could not construct match logs URL")
        scraped_done[player_name] = "url_error"
        failed_players.append(player_name)
        continue
    
    print(f"    Match logs: {logs_url}")
    
    # Step 3: Scrape match logs
    df, status = scrape_match_log_page(logs_url, player_name)
    time.sleep(5)  # Rate limit between player pages
    
    if status == "rate_limited":
        print(f"    [RATE LIMITED] Sleeping 60s...")
        time.sleep(60)
        df, status = scrape_match_log_page(logs_url, player_name)
    
    if df is None or len(df) == 0:
        print(f"    [NO DATA] Status: {status}")
        scraped_done[player_name] = f"no_data:{status}"
        failed_players.append(player_name)
    else:
        print(f"    [SUCCESS] {len(df)} match log rows")
        df['Nation'] = "WC"
        df['league_'] = "Direct-Scrape"
        all_new_frames.append(df)
        found_players.append(player_name)
        scraped_done[player_name] = "found"
    
    # Save progress after each player
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(scraped_done, f, indent=2)

# ── 3. APPEND TO GLOBAL CSV ─────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"SCRAPE COMPLETE")
print(f"  Players found: {len(found_players)}")
print(f"  Players failed/not found: {len(failed_players)}")

if all_new_frames:
    new_data = pd.concat(all_new_frames, ignore_index=True)
    print(f"  New rows: {len(new_data):,}")
    
    # Harmonize columns - use only columns in existing
    common_cols = [c for c in existing_df.columns if c in new_data.columns]
    new_data_trimmed = new_data[common_cols].copy()
    
    combined = pd.concat([existing_df, new_data_trimmed], ignore_index=True)
    combined.to_csv(GLOBAL_CSV, index=False)
    
    print(f"\n  Updated: {GLOBAL_CSV}")
    print(f"  Total rows: {len(combined):,}")
    
    print(f"\nFound players:")
    for p in found_players:
        print(f"  + {p}")

print(f"\nFailed/Not on FBref:")
for p in failed_players[:20]:
    print(f"  - {p}")

print("\nDone!")
