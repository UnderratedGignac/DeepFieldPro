"""
odds_feed.py
------------
Live odds ingestion. Two modes:
  - Dev:  REST polling via The Odds API (no WebSocket, limited rate)
  - Prod: Betfair Exchange WebSocket stream via betfairlightweight 2.23+

BUG FIX (v2.23 API change):
  betfairlightweight 2.23 no longer passes raw JSON dicts to on_data().
  The library now handles parsing internally. Use listener.snap() to read
  MarketBook objects from the internal cache after streaming starts.

Performance fix:
  All DB writes are queued and written in batches by a background thread
  to avoid SQLite becoming a bottleneck under high-frequency tick data.
"""

import os
import queue
import sqlite3
import threading
import time
import requests
import betfairlightweight
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'odds_stream.db')

ODDS_API_KEY    = os.getenv('ODDS_API_KEY')
BETFAIR_APP_KEY = os.getenv('BETFAIR_APP_KEY')
BETFAIR_USERNAME = os.getenv('BETFAIR_USERNAME')
BETFAIR_PASSWORD = os.getenv('BETFAIR_PASSWORD')
BETFAIR_CERTS   = os.getenv('BETFAIR_CERTS_DIR')

# Thread-safe queue for batched DB writes
_write_queue = queue.Queue()


# ─────────────────────────────
# Database Setup
# ─────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS odds_feed (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id       TEXT,
        market_type    TEXT,
        player_id      TEXT,
        selection_name TEXT,
        price          REAL,
        volume         REAL,
        bookmaker      TEXT,
        timestamp      DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()


# ─────────────────────────────
# Batched DB Writer Thread
# ─────────────────────────────

def _db_writer_thread():
    """
    Background thread that drains the write queue and commits in batches.
    Prevents SQLite from being a bottleneck under high tick frequency.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    while True:
        try:
            # Block until at least one item is available
            item = _write_queue.get(timeout=1)
            batch = [item]

            # Drain the rest of the queue (non-blocking)
            while not _write_queue.empty():
                try:
                    batch.append(_write_queue.get_nowait())
                except queue.Empty:
                    break

            cursor.executemany('''
                INSERT INTO odds_feed (match_id, market_type, player_id, selection_name, price, volume, bookmaker)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', batch)
            conn.commit()

        except queue.Empty:
            continue
        except sqlite3.Error as e:
            print(f"DB Write Error: {e}")


def log_odds(match_id, market_type, player_id, selection_name, price, volume, bookmaker):
    """Non-blocking — puts odds onto the write queue."""
    _write_queue.put((match_id, market_type, player_id, selection_name, price, volume, bookmaker))


def start_db_writer():
    """Call once at startup to launch the background DB writer thread."""
    t = threading.Thread(target=_db_writer_thread, daemon=True)
    t.start()
    print("DB writer thread started.")


# ─────────────────────────────
# Dev: The Odds API (REST poll)
# ─────────────────────────────

def fetch_odds_dev(sport_key='soccer_epl', regions='uk', markets='h2h'):
    """
    Poll The Odds API for current odds. Use for development only.
    Prod should use Betfair WebSocket stream.
    """
    if not ODDS_API_KEY:
        print("Dev Error: ODDS_API_KEY not set in .env")
        return

    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds/'
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': regions,
        'markets': markets,
        'oddsFormat': 'decimal'
    }

    response = requests.get(url, params=params, timeout=10)
    if response.status_code == 200:
        data = response.json()
        count = 0
        for event in data:
            match_id = event['id']
            for bookmaker in event['bookmakers']:
                book_title = bookmaker['title']
                for market in bookmaker['markets']:
                    market_type = market['key']
                    for outcome in market['outcomes']:
                        log_odds(match_id, market_type, None,
                                 outcome['name'], outcome['price'], 0.0, book_title)
                        count += 1
        print(f"Dev: Queued {count} odds rows for DB write.")
    else:
        print(f"Dev Error: {response.status_code} — {response.text}")


# ─────────────────────────────
# Prod: Betfair Exchange WebSocket (betfairlightweight 2.23+)
# ─────────────────────────────

def start_betfair_stream(market_ids):
    """
    Start a Betfair Exchange WebSocket stream for a list of market IDs.
    Reads MarketBook objects from the library's internal cache via listener.snap().

    market_ids: list of strings e.g. ['1.234567890']
    """
    if not all([BETFAIR_APP_KEY, BETFAIR_USERNAME, BETFAIR_PASSWORD, BETFAIR_CERTS]):
        print("Prod Error: Betfair credentials missing in .env")
        return

    trading = betfairlightweight.APIClient(
        username=BETFAIR_USERNAME,
        password=BETFAIR_PASSWORD,
        app_key=BETFAIR_APP_KEY,
        certs=BETFAIR_CERTS
    )
    trading.login()

    # betfairlightweight 2.23+: Use StreamListener with internal caching
    listener = betfairlightweight.StreamListener(max_latency=None)
    stream = trading.streaming.create_stream(listener=listener)

    market_filter = betfairlightweight.filters.streaming_market_filter(
        market_ids=market_ids
    )
    market_data_filter = betfairlightweight.filters.streaming_market_data_filter(
        fields=["EX_BEST_OFFERS", "EX_TRADED_VOL", "EX_LTP"],
        ladder_levels=3
    )

    stream.subscribe_to_markets(
        market_filter=market_filter,
        market_data_filter=market_data_filter,
        conflate_ms=500   # Throttle to 1 update per 500ms per market
    )

    print(f"Starting Betfair WebSocket stream for markets: {market_ids}")
    stream.start(async_=True)  # Non-blocking: runs in background thread

    # Poll the snapshot cache in a loop
    try:
        while True:
            market_books = listener.snap()  # Returns list of MarketBook objects
            for market_book in market_books:
                market_id = market_book.market_id
                for runner in market_book.runners:
                    ltp = runner.last_price_traded
                    tv  = runner.total_matched or 0.0
                    if ltp:
                        log_odds(
                            market_id, 'exchange',
                            str(runner.selection_id),
                            str(runner.selection_id),  # Resolve name via catalog separately
                            ltp, tv, 'Betfair Exchange'
                        )
            time.sleep(0.5)  # Match conflate_ms setting
    except KeyboardInterrupt:
        print("Betfair stream stopped.")


if __name__ == '__main__':
    init_db()
    start_db_writer()
    print("Odds feed initialized. Tables created and writer thread started.")
    # Uncomment to test dev mode:
    # fetch_odds_dev()
