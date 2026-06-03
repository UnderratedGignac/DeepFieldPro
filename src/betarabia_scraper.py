import asyncio
import sqlite3
import random
import logging
import os
import datetime
from playwright.async_api import async_playwright, TimeoutError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'odds_stream.db')
ERROR_LOG_PATH = os.path.join(BASE_DIR, 'data', 'scraper_errors.log')

# Helper to initialize DB schema
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
      CREATE TABLE IF NOT EXISTS fixture (
        fixture_id TEXT PRIMARY KEY,
        home_team TEXT,
        away_team TEXT,
        kickoff_time TEXT,
        league_id TEXT,
        scraped_at TEXT
      )
    """)
    cursor.execute("""
      CREATE TABLE IF NOT EXISTS market (
        market_id TEXT PRIMARY KEY,
        fixture_id TEXT,
        market_name TEXT,
        selection_name TEXT,
        raw_odds REAL,
        prop_player TEXT,
        prop_type TEXT,
        prop_line REAL,
        scraped_at TEXT
      )
    """)
    conn.commit()
    conn.close()

async def random_delay():
    # Random delay to mimic human behavior
    await asyncio.sleep(random.uniform(1.5, 3.5))

def is_player_prop(MarketName_P: str) -> bool:
    keywords = ["shots", "passes", "tackles", "cards", "goals", "assists", "to score", "shots on target", "pass attempts"]
    return any(k in MarketName_P.lower() for k in keywords)

def parse_player_prop(SelectionName_P: str, MarketName_P: str):
    # Very rudimentary parsing logic. Real scraper needs regex for specific bookmaker format.
    # e.g., SelectionName_V: "Chris Wood Over 0.5" -> PlayerName_V="Chris Wood", PropType_V="SoT", Line_V=0.5
    parts = SelectionName_P.split(' Over ')
    if len(parts) == 2:
        return parts[0].strip(), MarketName_P, float(parts[1].strip())
    
    parts = SelectionName_P.split(' Under ')
    if len(parts) == 2:
        return parts[0].strip(), MarketName_P, float(parts[1].strip())
        
    return None, None, None

async def scrape_fixture_markets(page, FixtureId_P: str):
    # Dummy mock of scraping since we don't have access to the live HTML structure
    markets = []
    
    # Mock some player prop markets
    markets.append({
        "MarketId_V": f"{FixtureId_P}_passes_01",
        "MarketName_V": "Player Passes Over 30.5",
        "SelectionName_V": "Chris Wood Over 30.5",
        "RawOdds_V": 1.85
    })
    
    markets.append({
        "MarketId_V": f"{FixtureId_P}_sot_01",
        "MarketName_V": "Player Shots on Target Over 0.5",
        "SelectionName_V": "Robert Lewandowski Over 0.5",
        "RawOdds_V": 2.10
    })
    
    # Mock some match result markets
    markets.append({
        "MarketId_V": f"{FixtureId_P}_1X2_home",
        "MarketName_V": "Match Result",
        "SelectionName_V": "Home Win",
        "RawOdds_V": 2.50
    })
    return markets

async def run_scraper():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    fixtures_scraped = 0
    markets_scraped = 0
    player_props_found = 0
    fixtures_no_props = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # Note: actual betarabia URL needs to be reached. We mock the scraping logic since it's a live protected site.
            logger.info("Navigating to betarabia.com...")
            # await page.goto("https://www.betarabia.com/football", timeout=60000)
            await random_delay()
            
            # MOCK DATA FOR DEMO PURPOSES
            fixtures = [
                {"FixtureId_V": "fix_001", "HomeTeam_V": "Team A", "AwayTeam_V": "Team B", "KickoffTime_V": "20:00", "LeagueId_V": "ENG_PL"}
            ]
            
            for fix in fixtures:
                try:
                    # Retry logic with exponential backoff
                    for attempt in range(3):
                        try:
                            # await page.goto(f"https://www.betarabia.com/fixture/{fix['FixtureId_V']}")
                            await random_delay()
                            break # Success
                        except TimeoutError:
                            logger.warning(f"Attempt {attempt+1} failed for {fix['FixtureId_V']}")
                            await asyncio.sleep(2 ** attempt)
                            if attempt == 2: raise
                    
                    ScrapedAt_V = datetime.datetime.utcnow().isoformat()
                    cursor.execute("""
                        INSERT OR REPLACE INTO fixture (fixture_id, home_team, away_team, kickoff_time, league_id, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (fix["FixtureId_V"], fix["HomeTeam_V"], fix["AwayTeam_V"], fix["KickoffTime_V"], fix["LeagueId_V"], ScrapedAt_V))
                    fixtures_scraped += 1
                    
                    markets = await scrape_fixture_markets(page, fix["FixtureId_V"])
                    
                    props_in_fix = 0
                    for m in markets:
                        PlayerName_V, PropType_V, Line_V = None, None, None
                        if is_player_prop(m["MarketName_V"]):
                            PlayerName_V, PropType_V, Line_V = parse_player_prop(m["SelectionName_V"], m["MarketName_V"])
                            if PlayerName_V:
                                props_in_fix += 1
                                player_props_found += 1
                                
                        cursor.execute("""
                            INSERT OR REPLACE INTO market (market_id, fixture_id, market_name, selection_name, raw_odds, prop_player, prop_type, prop_line, scraped_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (m["MarketId_V"], fix["FixtureId_V"], m["MarketName_V"], m["SelectionName_V"], m["RawOdds_V"], PlayerName_V, PropType_V, Line_V, ScrapedAt_V))
                        markets_scraped += 1
                        
                    if props_in_fix == 0:
                        fixtures_no_props += 1
                        
                except Exception as e:
                    with open(ERROR_LOG_PATH, 'a') as f:
                        f.write(f"[{datetime.datetime.utcnow().isoformat()}] Error scraping fixture {fix['FixtureId_V']}: {str(e)}\n")
                    logger.error(f"Failed to scrape {fix['FixtureId_V']}. Skipping.")
                    
        finally:
            await browser.close()
            conn.commit()
            conn.close()
            
    print("\n--- SCRAPER HEALTH CHECK ---")
    print(f"Fixtures scraped       : {fixtures_scraped}")
    print(f"Markets scraped        : {markets_scraped}")
    print(f"Player props found     : {player_props_found}")
    print(f"Fixtures with no props : {fixtures_no_props}")
    print("----------------------------\n")

if __name__ == "__main__":
    asyncio.run(run_scraper())
