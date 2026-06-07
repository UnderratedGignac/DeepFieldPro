"""
DeepFieldPro — Global League Data Fetcher
==========================================
Industrial-grade scraper for API-Football that fetches ALL player data 
across ALL leagues worldwide.

FEATURES:
- Uses SQLite to track progress (resumes automatically if interrupted)
- Handles API pagination automatically
- Respects rate limits (10 req/sec, tracks daily quota)
- Saves all player stats to a unified master CSV

NOTE: To fetch "all leagues in the world", you need a paid API-Football plan.
The Free plan (100 req/day) will take a very long time to complete.
"""

import requests
import sqlite3
import pandas as pd
import time
import os
import sys

# ─── Configuration ────────────────────────────────────────────────────────
API_KEY     = '4ae9f07e1ae1f775050015c50037a71d'
API_HEADERS = {'x-apisports-key': API_KEY}
BASE_URL    = 'https://v3.football.api-sports.io'
TARGET_SEASON = 2024

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
DB_PATH = os.path.join(DATA_DIR, 'sync_state.db')
MASTER_CSV = os.path.join(DATA_DIR, 'global_players_master.csv')

os.makedirs(DATA_DIR, exist_ok=True)

# ─── Setup DB ─────────────────────────────────────────────────────────────
def init_db():
    """Tracks which leagues and pages have already been successfully scraped."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS league_sync (
            league_id INTEGER,
            season INTEGER,
            total_pages INTEGER DEFAULT 0,
            pages_fetched INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING',
            PRIMARY KEY (league_id, season)
        )
    ''')
    conn.commit()
    return conn

def check_api_status():
    """Check remaining API requests for the day."""
    try:
        r = requests.get(f'{BASE_URL}/status', headers=API_HEADERS, timeout=10)
        data = r.json()
        reqs = data.get('response', {}).get('requests', {})
        used = reqs.get('current', 0)
        limit = reqs.get('limit_day', 100)
        return used, limit
    except Exception as e:
        print(f"Error checking API status: {e}")
        return 0, 100

def get_all_leagues(conn):
    """Fetch all available leagues from the API and add them to the sync DB."""
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM league_sync WHERE season = ?', (TARGET_SEASON,))
    if c.fetchone()[0] > 0:
        print(f"[+] Leagues already loaded in sync DB for season {TARGET_SEASON}.")
        return

    print("[+] Fetching master league list from API-Football...")
    r = requests.get(f'{BASE_URL}/leagues', headers=API_HEADERS)
    if r.status_code != 200:
        print("Failed to fetch leagues.")
        return

    leagues = r.json().get('response', [])
    inserted = 0
    for l in leagues:
        lid = l['league']['id']
        c.execute('''
            INSERT OR IGNORE INTO league_sync (league_id, season, status) 
            VALUES (?, ?, 'PENDING')
        ''', (lid, TARGET_SEASON))
        inserted += 1
    
    conn.commit()
    print(f"[+] Added {inserted} leagues to sync queue.")

def fetch_player_page(league_id, season, page):
    """Fetch a single page of players for a league."""
    print(f"    -> Fetching L{league_id} Page {page}...")
    r = requests.get(f'{BASE_URL}/players', headers=API_HEADERS, 
                     params={'league': league_id, 'season': season, 'page': page})
    
    if r.status_code == 429 or 'requests limit reached' in r.text.lower():
        print("    [!] API Daily Limit Reached! Pausing for 24 hours...")
        time.sleep(86400) # 24 hours
        return fetch_player_page(league_id, season, page)
        
    data = r.json()
    if 'errors' in data and data['errors']:
        print(f"    [!] Error: {data['errors']}")
        if data['errors'].get('rateLimit'):
            print("    [!] Rate limit triggered, sleeping 60s...")
            time.sleep(60)
            return fetch_player_page(league_id, season, page)
            
    return data

def process_players(data, league_id):
    """Convert JSON player response to flat DataFrame."""
    rows = []
    players = data.get('response', [])
    for p in players:
        info = p.get('player', {})
        stats_list = p.get('statistics', [])
        
        # A player might have multiple stat blocks if they changed teams, sum or take the target league one
        for st in stats_list:
            if st.get('league', {}).get('id') == league_id:
                games = st.get('games', {})
                goals = st.get('goals', {})
                passes = st.get('passes', {})
                shots = st.get('shots', {})
                cards = st.get('cards', {})
                
                rows.append({
                    'player_id': info.get('id'),
                    'player_name': info.get('name'),
                    'age': info.get('age'),
                    'nationality': info.get('nationality'),
                    'league_id': league_id,
                    'season': TARGET_SEASON,
                    'team_id': st.get('team', {}).get('id'),
                    'team_name': st.get('team', {}).get('name'),
                    'position': games.get('position'),
                    'minutes': games.get('minutes', 0),
                    'appearences': games.get('appearences', 0),
                    'goals': goals.get('total', 0),
                    'assists': goals.get('assists', 0),
                    'shots_total': shots.get('total', 0),
                    'shots_on': shots.get('on', 0),
                    'passes_total': passes.get('total', 0),
                    'passes_key': passes.get('key', 0),
                    'cards_yellow': cards.get('yellow', 0),
                    'cards_red': cards.get('red', 0),
                    'rating': games.get('rating')
                })
                break # Just take the stats for the target league
    
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

def save_to_csv(df):
    """Append DataFrame to master CSV."""
    if df.empty: return
    # If file exists, append without headers
    header = not os.path.exists(MASTER_CSV)
    df.to_csv(MASTER_CSV, mode='a', header=header, index=False)

def run_sync():
    print("=" * 60)
    print("DeepFieldPro — GLOBAL LEAGUE DATA FETCHER (ENDLESS GOAL MODE)")
    print("=" * 60)
    
    while True:
        used, limit = check_api_status()
        print(f"\n[{time.strftime('%H:%M:%S')}] API Quota: {used} / {limit} requests used today.")
        if used >= limit:
            print("Daily limit already reached. Sleeping for 24 hours...")
            time.sleep(86400)
            continue

        conn = init_db()
        get_all_leagues(conn)
        
        c = conn.cursor()
        c.execute("SELECT league_id, total_pages, pages_fetched FROM league_sync WHERE status = 'PENDING' ORDER BY league_id ASC")
        pending = c.fetchall()
        
        if not pending:
            print("[+] All leagues globally have been successfully synced!")
            sys.exit(0)
            
        print(f"[+] {len(pending)} leagues waiting to be synced.")
        
        for lid, total_p, fetched_p in pending:
            print(f"\n[*] Processing League {lid}...")
        
            # Initial request to get page 1 and total pages
            start_page = fetched_p + 1
            
            try:
                data = fetch_player_page(lid, TARGET_SEASON, start_page)
                paging = data.get('paging', {})
                total_pages = paging.get('total', 1)
                
                # Process page 1 (or whatever start_page is)
                df = process_players(data, lid)
                save_to_csv(df)
                
                # Update DB state
                c.execute("UPDATE league_sync SET total_pages = ?, pages_fetched = ? WHERE league_id = ? AND season = ?", 
                          (total_pages, start_page, lid, TARGET_SEASON))
                conn.commit()
                
                # Loop through remaining pages
                for page in range(start_page + 1, total_pages + 1):
                    data = fetch_player_page(lid, TARGET_SEASON, page)
                    df = process_players(data, lid)
                    save_to_csv(df)
                    
                    c.execute("UPDATE league_sync SET pages_fetched = ? WHERE league_id = ? AND season = ?", 
                              (page, lid, TARGET_SEASON))
                    conn.commit()
                    time.sleep(1) # Base rate limit padding
                    
                # Mark complete
                c.execute("UPDATE league_sync SET status = 'COMPLETED' WHERE league_id = ? AND season = ?", (lid, TARGET_SEASON))
                conn.commit()
                print(f"    [OK] League {lid} Complete! ({total_pages} pages)")
                
            except KeyboardInterrupt:
                print("\n[!] Sync paused by user. Progress is saved in sync_state.db.")
                sys.exit(0)
            except Exception as e:
                print(f"    [!] Unhandled error on league {lid}: {e}")
                time.sleep(5)
                continue
            
    print("\n[+] Global sync cycle completed! Will check again for any missed data.")

if __name__ == '__main__':
    run_sync()
