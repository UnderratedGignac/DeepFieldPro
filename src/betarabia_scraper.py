# mypy: ignore-errors
import asyncio
import sqlite3
import random
import logging
import os
import datetime
import json
from playwright.async_api import async_playwright, TimeoutError

# Set BETARABIA_HEADLESS=false in terminal to debug visually
HEADLESS_MODE = os.environ.get("BETARABIA_HEADLESS", "true").lower() != "false"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "odds_stream.db")
ERROR_LOG_PATH = os.path.join(BASE_DIR, "data", "scraper_errors.log")
PROBE_PATH = os.path.join(BASE_DIR, "data", "betarabia_page_probe.html")
SCREENSHOT_PATH = os.path.join(BASE_DIR, "data", "betarabia_screenshot.png")
API_RESPONSES_PATH = os.path.join(BASE_DIR, "data", "betarabia_api_responses.json")


def init_db():
    Conn_V = sqlite3.connect(DB_PATH)
    Cursor_V = Conn_V.cursor()
    Cursor_V.execute("""
      CREATE TABLE IF NOT EXISTS fixture (
        fixture_id TEXT PRIMARY KEY,
        home_team TEXT,
        away_team TEXT,
        kickoff_time TEXT,
        league_id TEXT,
        scraped_at TEXT
      )
    """)
    Cursor_V.execute("""
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
    Conn_V.commit()
    Conn_V.close()


async def random_delay():
    await asyncio.sleep(random.uniform(1.5, 3.5))


async def _safe_inner_text(El_P, Selector_P: str) -> str:
    for SingleSel_V in Selector_P.split(","):
        try:
            Child_V = await El_P.query_selector(SingleSel_V.strip())
            if Child_V:
                Text_V = await Child_V.inner_text()
                if Text_V and Text_V.strip():
                    return Text_V.strip()
        except Exception:
            continue
    return ""


def _parse_odds(OddsText_P: str) -> float | None:
    if not OddsText_P:
        return None
    try:
        Cleaned_V = OddsText_P.strip().replace(",", ".")
        Value_V = float(Cleaned_V)
        if 1.01 <= Value_V <= 100.0:
            return Value_V
        return None
    except (ValueError, TypeError):
        return None


def is_player_prop(MarketName_P: str) -> bool:
    Keywords_V = [
        "shots",
        "passes",
        "tackles",
        "cards",
        "goals",
        "assists",
        "to score",
        "shots on target",
        "pass attempts",
    ]
    return any(K_V in MarketName_P.lower() for K_V in Keywords_V)


def parse_player_prop(SelectionName_P: str, MarketName_P: str):
    Parts_V = SelectionName_P.split(" Over ")
    if len(Parts_V) == 2:
        return Parts_V[0].strip(), MarketName_P, float(Parts_V[1].strip())
    Parts_V = SelectionName_P.split(" Under ")
    if len(Parts_V) == 2:
        return Parts_V[0].strip(), MarketName_P, float(Parts_V[1].strip())
    return None, None, None


async def run_full_probe(Page_P) -> None:
    # Save complete HTML to file for inspection
    FullHtml_V = await Page_P.content()
    with open(PROBE_PATH, "w", encoding="utf-8") as F_V:
        F_V.write(FullHtml_V)

    # Save screenshot so we can see what the browser actually rendered
    await Page_P.screenshot(path=SCREENSHOT_PATH, full_page=True)

    # Log key stats
    BodyLen_V = len(FullHtml_V)
    HasBody_V = "<body" in FullHtml_V
    HasDiv_V = "<div" in FullHtml_V
    logger.info(f"HTML length  : {BodyLen_V} chars")
    logger.info(f"Has <body>   : {HasBody_V}")
    logger.info(f"Has <div>    : {HasDiv_V}")
    logger.info(f"Full HTML → {PROBE_PATH}")
    logger.info(f"Screenshot → {SCREENSHOT_PATH}")


def parse_fixtures_from_api(ApiResponses_P: list) -> list:
    Fixtures_V = []

    for Response_V in ApiResponses_P:
        Data_V = Response_V.get("data", {})
        Url_V = Response_V.get("url", "")

        # Try unwrapping common API envelope patterns
        if isinstance(Data_V, dict):
            # Try common root keys
            for RootKey_V in [
                "data",
                "result",
                "events",
                "fixtures",
                "matches",
                "items",
            ]:
                if RootKey_V in Data_V:
                    Data_V = Data_V[RootKey_V]
                    break

        if not isinstance(Data_V, list):
            continue

        for Item_V in Data_V:
            if not isinstance(Item_V, dict):
                continue

            # Try common field name patterns for home/away teams
            HomeTeam_V = (
                Item_V.get("homeTeam")
                or Item_V.get("home_team")
                or Item_V.get("home")
                or Item_V.get("localTeam", {}).get("name")
                or Item_V.get("team1")
            )
            AwayTeam_V = (
                Item_V.get("awayTeam")
                or Item_V.get("away_team")
                or Item_V.get("away")
                or Item_V.get("visitorTeam", {}).get("name")
                or Item_V.get("team2")
            )
            KickoffTime_V = (
                Item_V.get("startTime")
                or Item_V.get("kickoff")
                or Item_V.get("start_time")
                or Item_V.get("scheduled")
                or Item_V.get("time")
                or "TBD"
            )
            FixtureId_V = str(
                Item_V.get("id")
                or Item_V.get("eventId")
                or Item_V.get("fixture_id")
                or f"{HomeTeam_V}_{AwayTeam_V}"
            )
            FixtureUrl_V = (
                Item_V.get("url") or Item_V.get("link") or f"/en/event/{FixtureId_V}"
            )

            if HomeTeam_V and AwayTeam_V:
                Fixtures_V.append(
                    {
                        "FixtureId_V": FixtureId_V,
                        "HomeTeam_V": str(HomeTeam_V),
                        "AwayTeam_V": str(AwayTeam_V),
                        "KickoffTime_V": str(KickoffTime_V),
                        "LeagueId_V": str(
                            Item_V.get("league")
                            or Item_V.get("competition")
                            or "FOOTBALL"
                        ),
                        "FixtureUrl_V": str(FixtureUrl_V),
                        "RawApiItem_V": Item_V,
                    }
                )

        if Fixtures_V:
            logger.info(f"Parsed {len(Fixtures_V)} fixtures from: {Url_V}")
            break  # Stop at first successful parse

    return Fixtures_V


def parse_markets_from_api_item(ApiItem_P: dict, FixtureId_P: str) -> list:
    Markets_V = []

    # Try common market container keys
    MarketData_V = (
        ApiItem_P.get("markets")
        or ApiItem_P.get("odds")
        or ApiItem_P.get("betOffers")
        or ApiItem_P.get("selections")
        or []
    )

    if not isinstance(MarketData_V, list):
        return Markets_V

    for MktIdx_V, Mkt_V in enumerate(MarketData_V):
        if not isinstance(Mkt_V, dict):
            continue

        MarketName_V = (
            Mkt_V.get("name")
            or Mkt_V.get("marketName")
            or Mkt_V.get("type")
            or f"market_{MktIdx_V}"
        )

        Outcomes_V = (
            Mkt_V.get("outcomes")
            or Mkt_V.get("selections")
            or Mkt_V.get("runners")
            or []
        )

        for SelIdx_V, Sel_V in enumerate(Outcomes_V):
            if not isinstance(Sel_V, dict):
                continue

            SelectionName_V = (
                Sel_V.get("name")
                or Sel_V.get("label")
                or Sel_V.get("description")
                or f"selection_{SelIdx_V}"
            )

            # Try decimal odds first, then convert American/fractional
            RawOdds_V = (
                Sel_V.get("decimalOdds")
                or Sel_V.get("decimal")
                or Sel_V.get("odds")
                or Sel_V.get("price")
                or Sel_V.get("value")
            )

            try:
                RawOdds_V = float(RawOdds_V)
                if not (1.01 <= RawOdds_V <= 100.0):
                    continue
            except (TypeError, ValueError):
                continue

            Markets_V.append(
                {
                    "MarketId_V": f"{FixtureId_P}_{MktIdx_V}_{SelIdx_V}",
                    "MarketName_V": str(MarketName_V),
                    "SelectionName_V": str(SelectionName_V),
                    "RawOdds_V": RawOdds_V,
                }
            )

    return Markets_V


async def scrape_fixture_list(Page_P) -> list:
    # HTML Fallback approach
    try:
        await Page_P.wait_for_selector(
            "[class*='event'], [class*='fixture'], [class*='match']", timeout=15000
        )
    except TimeoutError:
        logger.warning("No fixtures found on page within timeout.")
        return []

    FixtureElements_V = await Page_P.query_selector_all(
        "[class*='event-row'], [class*='fixture-row'], "
        "[class*='match-row'], [class*='event-item']"
    )

    Fixtures_V = []
    for El_V in FixtureElements_V:
        try:
            HomeTeam_V = await _safe_inner_text(
                El_V,
                "[class*='home'], [class*='team-home'], [class*='participant']:first-child",
            )
            AwayTeam_V = await _safe_inner_text(
                El_V,
                "[class*='away'], [class*='team-away'], [class*='participant']:last-child",
            )
            KickoffTime_V = await _safe_inner_text(
                El_V, "[class*='time'], [class*='kickoff'], [class*='start-time']"
            )

            if HomeTeam_V and AwayTeam_V:
                FixtureId_V = f"{HomeTeam_V.strip().lower().replace(' ', '_')}_vs_{AwayTeam_V.strip().lower().replace(' ', '_')}"
                FixtureUrl_V = await El_V.get_attribute("href")
                if not FixtureUrl_V:
                    LinkEl_V = await El_V.query_selector("a")
                    if LinkEl_V:
                        FixtureUrl_V = await LinkEl_V.get_attribute("href")

                Fixtures_V.append(
                    {
                        "FixtureId_V": FixtureId_V,
                        "HomeTeam_V": HomeTeam_V.strip(),
                        "AwayTeam_V": AwayTeam_V.strip(),
                        "KickoffTime_V": (
                            KickoffTime_V.strip() if KickoffTime_V else "TBD"
                        ),
                        "LeagueId_V": "FOOTBALL",
                        "FixtureUrl_V": FixtureUrl_V or "",
                    }
                )
        except Exception as E_V:
            logger.warning(f"Failed to parse fixture element: {E_V}")
            continue

    return Fixtures_V


async def scrape_fixture_markets(Page_P, FixtureUrl_P: str, FixtureId_P: str) -> list:
    # HTML Fallback approach
    Markets_V = []

    try:
        if FixtureUrl_P:
            FullUrl_V = (
                f"https://betarabia.com{FixtureUrl_P}"
                if FixtureUrl_P.startswith("/")
                else FixtureUrl_P
            )
            await Page_P.goto(FullUrl_V, wait_until="networkidle", timeout=20000)
            await random_delay()

        ExpandBtns_V = await Page_P.query_selector_all(
            "[class*='expand'], [class*='show-more'], "
            "[class*='toggle'], [aria-expanded='false']"
        )
        for Btn_V in ExpandBtns_V:
            try:
                await Btn_V.click()
                await asyncio.sleep(0.5)
            except Exception:
                pass

        MarketBlocks_V = await Page_P.query_selector_all(
            "[class*='market'], [class*='bet-group'], "
            "[class*='market-group'], [class*='odds-group']"
        )

        for BlockIdx_V, Block_V in enumerate(MarketBlocks_V):
            try:
                MarketName_V = await _safe_inner_text(
                    Block_V,
                    "[class*='market-name'], [class*='group-title'], [class*='header'], h3, h4",
                )
                if not MarketName_V:
                    MarketName_V = f"market_{BlockIdx_V}"

                SelectionEls_V = await Block_V.query_selector_all(
                    "[class*='outcome'], [class*='selection'], "
                    "[class*='bet-option'], [class*='odd-item']"
                )

                for SelIdx_V, SelEl_V in enumerate(SelectionEls_V):
                    try:
                        SelectionName_V = await _safe_inner_text(
                            SelEl_V,
                            "[class*='name'], [class*='label'], [class*='selection-name'], span:first-child",
                        )
                        OddsText_V = await _safe_inner_text(
                            SelEl_V,
                            "[class*='odd'], [class*='price'], [class*='odds-value'], span:last-child",
                        )

                        RawOdds_V = _parse_odds(OddsText_V)
                        if RawOdds_V is None:
                            continue

                        MarketId_V = f"{FixtureId_P}_{BlockIdx_V}_{SelIdx_V}"

                        Markets_V.append(
                            {
                                "MarketId_V": MarketId_V,
                                "MarketName_V": MarketName_V.strip(),
                                "SelectionName_V": (
                                    SelectionName_V.strip() if SelectionName_V else ""
                                ),
                                "RawOdds_V": RawOdds_V,
                            }
                        )

                    except Exception:
                        continue

            except Exception:
                continue

    except Exception as E_V:
        with open(ERROR_LOG_PATH, "a") as F_V:
            F_V.write(
                f"[{datetime.datetime.now(datetime.UTC).isoformat()}] Market scrape failed for {FixtureId_P}: {E_V}\n"
            )

    return Markets_V


async def run_scraper():
    init_db()
    Conn_V = sqlite3.connect(DB_PATH)
    Cursor_V = Conn_V.cursor()

    FixturesScraped_V = 0
    MarketsScraped_V = 0
    PlayerPropsFound_V = 0
    FixturesNoProps_V = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS_MODE)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = await context.new_page()

        ApiResponses_V = []

        # Capture every XHR/fetch response that looks like fixture data
        async def handle_response(Response_P):
            Url_V = Response_P.url
            # Target endpoints that likely contain fixture/odds data
            KeywordMatches_V = [
                "fixture",
                "match",
                "event",
                "sport",
                "odds",
                "market",
                "football",
                "soccer",
                "bet",
            ]
            if any(Kw_V in Url_V.lower() for Kw_V in KeywordMatches_V):
                try:
                    if "json" in Response_P.headers.get("content-type", ""):
                        JsonData_V = await Response_P.json()
                        ApiResponses_V.append({"url": Url_V, "data": JsonData_V})
                        logger.info(f"Captured API response: {Url_V}")
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            logger.info("Navigating to betarabia.com/en/sports/football...")
            # Navigate to betarabia football section
            await page.goto(
                "https://www.betarabia.com/en/sports/football",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            # Wait for the JS framework to mount something into the body
            try:
                await page.wait_for_function(
                    "document.body && document.body.children.length > 2", timeout=15000
                )
            except Exception:
                pass

            # Extra wait for dynamic content to render
            await asyncio.sleep(5)

            # Scroll to trigger lazy-loading of fixture cards
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

            # Accept cookies if banner appears
            try:
                CookieBtn_V = await page.query_selector(
                    "button[id*='accept'], button[class*='accept'], "
                    "button[class*='cookie']"
                )
                if CookieBtn_V:
                    await CookieBtn_V.click()
                    await random_delay()
            except Exception:
                pass

            with open(API_RESPONSES_PATH, "w") as F_V:
                json.dump(ApiResponses_V, F_V, indent=2)
            logger.info(f"Saved {len(ApiResponses_V)} API responses to inspect")

            # Try to parse fixtures from API first
            Fixtures_V = parse_fixtures_from_api(ApiResponses_V)
            ApiMode_V = len(Fixtures_V) > 0

            # HTML Fallback for fixtures if API failed
            if len(Fixtures_V) == 0:
                Fixtures_V = await scrape_fixture_list(page)

            if len(Fixtures_V) == 0:
                logger.warning("Zero fixtures found. Running page structure probe...")
                await run_full_probe(page)
            else:
                for Fix_V in Fixtures_V:
                    ScrapedAt_V = datetime.datetime.now(datetime.UTC).isoformat()
                    Cursor_V.execute(
                        """
                        INSERT OR REPLACE INTO fixture (fixture_id, home_team, away_team, kickoff_time, league_id, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            Fix_V["FixtureId_V"],
                            Fix_V["HomeTeam_V"],
                            Fix_V["AwayTeam_V"],
                            Fix_V["KickoffTime_V"],
                            Fix_V["LeagueId_V"],
                            ScrapedAt_V,
                        ),
                    )
                    FixturesScraped_V += 1

                    if ApiMode_V:
                        # Extract markets directly from the API item
                        Markets_V = parse_markets_from_api_item(
                            Fix_V.get("RawApiItem_V", {}), Fix_V["FixtureId_V"]
                        )
                    else:
                        # HTML Fallback approach for markets
                        for Attempt_V in range(3):
                            try:
                                await random_delay()
                                Markets_V = await scrape_fixture_markets(
                                    page,
                                    Fix_V.get("FixtureUrl_V", ""),
                                    Fix_V["FixtureId_V"],
                                )
                                break
                            except Exception as E_V:
                                logger.warning(
                                    f"Attempt {Attempt_V+1} failed for {Fix_V['FixtureId_V']}: {E_V}"
                                )
                                await asyncio.sleep(2**Attempt_V)
                                if Attempt_V == 2:
                                    with open(ERROR_LOG_PATH, "a") as F_V:
                                        F_V.write(
                                            f"[{datetime.datetime.now(datetime.UTC).isoformat()}] GAVE UP on {Fix_V['FixtureId_V']}\n"
                                        )
                                    Markets_V = []

                    PropsInFix_V = 0
                    for M_V in Markets_V:
                        PlayerName_V, PropType_V, Line_V = None, None, None
                        if is_player_prop(M_V["MarketName_V"]):
                            PlayerName_V, PropType_V, Line_V = parse_player_prop(
                                M_V["SelectionName_V"], M_V["MarketName_V"]
                            )
                            if PlayerName_V:
                                PropsInFix_V += 1
                                PlayerPropsFound_V += 1

                        Cursor_V.execute(
                            """
                            INSERT OR REPLACE INTO market (market_id, fixture_id, market_name, selection_name, raw_odds, prop_player, prop_type, prop_line, scraped_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                M_V["MarketId_V"],
                                Fix_V["FixtureId_V"],
                                M_V["MarketName_V"],
                                M_V["SelectionName_V"],
                                M_V["RawOdds_V"],
                                PlayerName_V,
                                PropType_V,
                                Line_V,
                                ScrapedAt_V,
                            ),
                        )
                        MarketsScraped_V += 1

                    if PropsInFix_V == 0:
                        FixturesNoProps_V += 1

        finally:
            await browser.close()
            Conn_V.commit()
            Conn_V.close()

    print("\n--- SCRAPER HEALTH CHECK ---")
    print(f"Fixtures scraped       : {FixturesScraped_V}")
    print(f"Markets scraped        : {MarketsScraped_V}")
    print(f"Player props found     : {PlayerPropsFound_V}")
    print(f"Fixtures with no props : {FixturesNoProps_V}")
    print("----------------------------\n")


if __name__ == "__main__":
    asyncio.run(run_scraper())

