"""
odds_scraper_betarabia.py
--------------------------
STEP 4: Live odds feed from Betarabia.

Since Betarabia has no public API, this scraper:
1. Uses requests + BeautifulSoup to pull odds from their live match pages
2. Parses player prop markets (passes over/under lines)
3. Writes matching odds rows to odds_stream.db every 30 seconds

Usage: Run in background alongside lineup_monitor.py
  python odds_scraper_betarabia.py
"""
import requests
import sqlite3
import time
import os
import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

DB_ODDS  = 'C:/Users/Elie/DeepFieldPro/data/odds_stream.db'
BASE_URL = 'https://www.betarabia.com'

# ── Headers that mimic a real browser ─────────────────────
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xhtml;q=0.9,*/*;q=0.8',
    'Referer': BASE_URL,
}

POLL_INTERVAL = 30  # seconds between scrapes

def init_db():
    conn = sqlite3.connect(DB_ODDS)
    conn.execute('''CREATE TABLE IF NOT EXISTS odds_feed (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id        TEXT,
        market_type     TEXT,
        player_id       TEXT,
        selection_name  TEXT,
        price           REAL,
        volume          REAL DEFAULT 0,
        bookmaker       TEXT DEFAULT 'Betarabia',
        timestamp       TEXT
    )''')
    conn.commit()
    conn.close()

def get_live_football_matches():
    """Scrape the Betarabia live/upcoming football matches page."""
    try:
        r = requests.get(f'{BASE_URL}/sports/football', headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print(f"Error fetching matches page: {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')

        matches = []
        # Look for JSON embedded in a script tag (common SPA pattern)
        for script in soup.find_all('script'):
            text = script.string or ''
            if 'fixtures' in text.lower() or 'events' in text.lower() or 'match' in text.lower():
                # Try to extract JSON blobs
                json_matches = re.findall(r'\{[^{}]*"id"\s*:\s*\d+[^{}]*\}', text)
                for jm in json_matches:
                    try:
                        obj = json.loads(jm)
                        if 'id' in obj:
                            matches.append(obj)
                    except Exception:
                        pass

        if not matches:
            # Fallback: parse HTML links to match pages
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/match/' in href or '/event/' in href:
                    match_id = re.search(r'/(\d+)', href)
                    if match_id:
                        matches.append({'id': match_id.group(1), 'url': href})

        print(f"Found {len(matches)} match links")
        return matches[:20]  # limit to 20 upcoming matches

    except Exception as e:
        print(f"Error fetching matches: {e}")
        return []

def scrape_player_props(match_id, match_url):
    """
    Try to scrape player prop markets (passes over/under) for a given match.
    Returns list of (selection_name, price) tuples.
    """
    odds_rows = []
    try:
        full_url = match_url if match_url.startswith('http') else f'{BASE_URL}{match_url}'
        r = requests.get(full_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        text = r.text

        # Pattern: look for "passes" or "Passes" near decimal odds
        # Decimal odds are floats between 1.01 and 50.0
        pass_pattern = re.findall(
            r'([A-Za-z\s]+(?:Pass|pass)[^\n"<]{0,60}?)\s*[:\-]?\s*(\d+\.\d{2})',
            text
        )
        for name, price in pass_pattern:
            try:
                price_float = float(price)
                if 1.01 <= price_float <= 20.0:
                    odds_rows.append({
                        'selection_name': name.strip()[:200],
                        'price':          price_float,
                    })
            except ValueError:
                pass

        # Also scan for any JSON-embedded odds
        for script in soup.find_all('script'):
            script_text = script.string or ''
            if 'pass' in script_text.lower() and 'price' in script_text.lower():
                try:
                    # Find JSON arrays/objects
                    blobs = re.findall(r'\{[^{}]{20,500}\}', script_text)
                    for blob in blobs:
                        try:
                            obj = json.loads(blob)
                            name = obj.get('name', obj.get('selection', obj.get('market', '')))
                            price = obj.get('price', obj.get('odds', obj.get('decimal', 0)))
                            if name and price and 'pass' in str(name).lower():
                                odds_rows.append({
                                    'selection_name': str(name)[:200],
                                    'price': float(price),
                                })
                        except Exception:
                            pass
                except Exception:
                    pass

    except Exception as e:
        print(f"  Error scraping match {match_id}: {e}")

    return odds_rows

def write_odds_to_db(match_id, odds_rows):
    """Write scraped odds rows to the database."""
    if not odds_rows:
        return 0

    conn = sqlite3.connect(DB_ODDS)
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    for row in odds_rows:
        conn.execute('''
            INSERT INTO odds_feed
            (match_id, market_type, player_id, selection_name, price, volume, bookmaker, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(match_id),
            'player_passes',
            '',
            row['selection_name'],
            row['price'],
            0.0,
            'Betarabia',
            now,
        ))
        written += 1
    conn.commit()
    conn.close()
    return written

def run():
    """Main scraping loop."""
    init_db()
    print(f"Betarabia Odds Scraper started. Polling every {POLL_INTERVAL}s...")
    print(f"Odds being written to: {DB_ODDS}\n")

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetching live matches...")
        matches = get_live_football_matches()

        total_written = 0
        for match in matches:
            match_id  = match.get('id', 'unknown')
            match_url = match.get('url', match.get('href', f'/match/{match_id}'))

            odds_rows = scrape_player_props(match_id, match_url)
            if odds_rows:
                written = write_odds_to_db(match_id, odds_rows)
                total_written += written
                print(f"  Match {match_id}: {written} odds rows written")

        print(f"Total written this cycle: {total_written}")
        print(f"Sleeping {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    run()
