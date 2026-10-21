# mypy: ignore-errors
"""
betarabia_scraper.py — DeepFieldPro Live Odds Scraper
======================================================
Targets the Kickertech (websbkt.com) API that powers betarabia.com/sports/kickertech.
Strategy:
  1. Navigate to betarabia.com/sports/kickertech to trigger API calls.
  2. Intercept XHR responses from api-m-sp-cdl.websbkt.com and pre-88o-sp.websbkt.com.
  3. Parse events (with real kickoff times) + odds directly from those API responses.
  4. Filter to TODAY's fixtures only (by kickoff_time date == today UTC).
  5. Upsert into odds_stream.db (fixture + market tables).
  6. Falls back to HTML scraping if API interception yields nothing.

NAMING CONVENTIONS:
  Parameters: ProperCase _P  |  Variables: ProperCase _V  |  SQL: lowercase/UPPERCASE
"""

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

# Set BETARABIA_DAYS_AHEAD to scrape fixtures N days ahead (default 0 = today only)
DAYS_AHEAD = int(os.environ.get("BETARABIA_DAYS_AHEAD", "0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "odds_stream.db")
ERROR_LOG_PATH = os.path.join(BASE_DIR, "data", "scraper_errors.log")
PROBE_PATH = os.path.join(BASE_DIR, "data", "betarabia_page_probe.html")
SCREENSHOT_PATH = os.path.join(BASE_DIR, "data", "betarabia_screenshot.png")
API_RESPONSES_PATH = os.path.join(BASE_DIR, "data", "betarabia_api_responses.json")

# Kickertech/SBTech API domains
SBTECH_DOMAINS = ["websbkt.com", "api-m-sp-cdl"]

# ─── API-capture memory bounds ───────────────────────────────────────────────
# The response handler used to append EVERY JSON response to an unbounded list
# while the same page was driven through 50 event navigations. Each navigation
# re-fetches the same boilerplate, so the list ended up holding ~50 copies of
# payloads the parsers never look at. Measured: one renderer at 1.34 GB.
#
# parse_kickertech_events()/parse_kickertech_odds() only read the top-level keys
# below, so anything else is dead weight. Dedup by URL collapses the repeats.
_PARSEABLE_KEYS = ("events", "odds", "data")
_MAX_CAPTURED_RESPONSES = 1500  # backstop against a pathological page
# Navigations before the page (and its renderer heap) is reset. Each betarabia
# event page is a full SPA load costing ~120 MB of renderer heap that is NOT
# released between same-origin navigations. Measured peaks per window:
#     no recycle -> 1341 MB      every 10 -> 901 MB      every 5 -> ~650 MB
# Closing the page does start a fresh renderer process (verified: the OS pid
# changes on every recycle), so the window size sets the peak directly.
# 3 keeps it near ~400 MB for about a second of extra page setup per batch.
_PAGE_RECYCLE_EVERY = 3


class _ResponseStore:
    """URL-keyed store of only the API payloads the parsers actually consume.

    Bounded three ways: SBTech domains only, parseable top-level keys only, and
    one entry per URL (latest wins) up to a hard cap.
    """

    def __init__(self):
        self._by_url = {}

    @staticmethod
    def _wanted(Url_P: str, Data_P) -> bool:
        if not isinstance(Data_P, dict):
            return False
        if not any(D_V in Url_P for D_V in SBTECH_DOMAINS):
            return False
        return any(K_V in Data_P for K_V in _PARSEABLE_KEYS)

    def add(self, Url_P: str, Data_P) -> bool:
        if not self._wanted(Url_P, Data_P):
            return False
        if (
            Url_P not in self._by_url
            and len(self._by_url) >= _MAX_CAPTURED_RESPONSES
        ):
            return False
        self._by_url[Url_P] = Data_P
        return True

    def as_list(self) -> list:
        """Shape the parsers expect: [{"url": ..., "data": ...}, ...]."""
        return [{"url": U_V, "data": D_V} for U_V, D_V in self._by_url.items()]

    def __len__(self):
        return len(self._by_url)


# How long to wait for an event's single-pre-event.json (the only source of
# O/U, BTTS and every other non-1X2 market). It lands ~3.5-4.5s after
# navigation on a warm page and later on a freshly recycled one.
_DEEP_FILE_TIMEOUT_MS = 15000


async def _scout_event(page, eid, store) -> bool:
    """Open one event page and return once ITS deep-markets file is stored.

    A fixed 3s sleep after domcontentloaded raced the SPA: a body still in
    flight when the page navigated away or closed was lost, which on
    2026-10-21 captured 2 of 50 events. Returns False (never raises) when the
    event serves no deep file in time.
    """
    url = f"https://www.betarabia.com/en/sports/kickertech/football/event/{eid}"
    marker = f"/lb/{eid}/single-pre-event.json"
    try:
        async with page.expect_response(
            lambda r: marker in r.url, timeout=_DEEP_FILE_TIMEOUT_MS
        ) as deep_info:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        deep = await deep_info.value
        store.add(deep.url, await deep.json())
        return True
    except Exception as e:
        logger.warning(f"No deep markets captured for event {eid}: {e}")
        return False

# Market name mapping from SBTech oddCode → human-readable
ODD_CODE_MAP = {
    # Match result
    "ODD_FTB_1X2_HOME": "Match Result",
    "ODD_FTB_1X2_DRAW": "Match Result",
    "ODD_FTB_1X2_AWAY": "Match Result",
    # BTTS
    "ODD_FTB_BOTHTEAMSSCORE_YES": "Both teams to score",
    "ODD_FTB_BOTHTEAMSSCORE_NO": "Both teams to score",
    # Total goals (both code variants)
    "ODD_FTB_TOTALS_OVER": "Total Goals",
    "ODD_FTB_TOTALS_UNDER": "Total Goals",
    "ODD_TTL_1_OVR": "Total Goals",
    "ODD_TTL_1_UND": "Total Goals",
    # Double chance
    "ODD_FTB_DC_1X": "Double Chance",
    "ODD_FTB_DC_X2": "Double Chance",
    "ODD_FTB_DC_12": "Double Chance",
    # Corners — CORRECTED: real API uses ODD_CRN_TTL_OVR (old map had wrong code)
    "ODD_CRN_TTL_OVR": "Total Corners",
    "ODD_CRN_TTL_UND": "Total Corners",
    "ODD_CRN_S1": "Team Corners",
    "ODD_CRN_S2": "Team Corners",
    # Legacy corner codes (may appear in deep-market files)
    "ODD_CORNER_TTL_OVR": "Total Corners",
    "ODD_CORNER_TTL_UND": "Total Corners",
    # Yellow cards / bookings
    "ODD_YEL_S1": "Team Yellow Cards",
    "ODD_YEL_S2": "Team Yellow Cards",
    "ODD_CARD_TTL_OVR": "Total Cards",
    "ODD_CARD_TTL_UND": "Total Cards",
    "ODD_YEL_TTL_OVR": "Total Yellow Cards",
    "ODD_YEL_TTL_UND": "Total Yellow Cards",
    # Match-level totals (shots on target, offsides)
    "ODD_SFG_TTL_OVR": "Total Shots on Target",
    "ODD_SOF_TTL_OVR": "Total Offsides",
}


def init_db():
    """Initialize SQLite DB with fixture and market tables + kickoff_date column."""
    Conn_V = sqlite3.connect(DB_PATH)
    Cursor_V = Conn_V.cursor()
    Cursor_V.execute(
        """
      CREATE TABLE IF NOT EXISTS fixture (
        fixture_id TEXT PRIMARY KEY,
        home_team TEXT,
        away_team TEXT,
        kickoff_time TEXT,
        kickoff_date TEXT,
        league_id TEXT,
        tournament_name TEXT,
        scraped_at TEXT
      )
    """
    )
    Cursor_V.execute(
        """
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
    """
    )
    # Migration: add kickoff_date and tournament_name if they don't exist
    try:
        Cursor_V.execute("ALTER TABLE fixture ADD COLUMN kickoff_date TEXT")
    except Exception:
        pass
    try:
        Cursor_V.execute("ALTER TABLE fixture ADD COLUMN tournament_name TEXT")
    except Exception:
        pass
    Conn_V.commit()
    Conn_V.close()


def purge_old_data(DaysOld_P: int = 3):
    """Delete fixtures/markets whose kickoff is more than DaysOld_P days in the past.
    Bounds DB growth and removes stale lingering duplicates. Safe: those matches are
    long finished and never bet again; today's and future data are untouched."""
    Cutoff_V = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=DaysOld_P)
    ).strftime("%Y-%m-%d")
    Conn_V = sqlite3.connect(DB_PATH)
    Cursor_V = Conn_V.cursor()
    Cursor_V.execute(
        "SELECT fixture_id FROM fixture WHERE kickoff_date < ?", (Cutoff_V,)
    )
    OldIds_V = [row[0] for row in Cursor_V.fetchall()]
    if OldIds_V:
        Placeholders_V = ",".join("?" for _ in OldIds_V)
        Cursor_V.execute(
            f"DELETE FROM market WHERE fixture_id IN ({Placeholders_V})", OldIds_V
        )
        Cursor_V.execute("DELETE FROM fixture WHERE kickoff_date < ?", (Cutoff_V,))
        logger.info(f"Purged {len(OldIds_V)} fixtures older than {Cutoff_V}.")
    Conn_V.commit()
    Conn_V.close()


def clear_todays_data(TodayStr_P: str):
    """
    Remove all fixture/market rows where kickoff_date matches today.
    This ensures we always work with fresh data on each run.
    """
    Conn_V = sqlite3.connect(DB_PATH)
    Cursor_V = Conn_V.cursor()
    # Get fixture_ids for today
    Cursor_V.execute(
        "SELECT fixture_id FROM fixture WHERE kickoff_date = ?", (TodayStr_P,)
    )
    TodayFixtureIds_V = [row[0] for row in Cursor_V.fetchall()]
    if TodayFixtureIds_V:
        Placeholders_V = ",".join("?" for _ in TodayFixtureIds_V)
        Cursor_V.execute(
            f"DELETE FROM market WHERE fixture_id IN ({Placeholders_V})",
            TodayFixtureIds_V,
        )
        Cursor_V.execute("DELETE FROM fixture WHERE kickoff_date = ?", (TodayStr_P,))
        logger.info(
            f"Cleared {len(TodayFixtureIds_V)} old fixtures for {TodayStr_P} before re-scraping."
        )
    Conn_V.commit()
    Conn_V.close()


async def random_delay():
    await asyncio.sleep(random.uniform(1.5, 3.5))


from typing import Optional  # noqa: E402


def _parse_odds(OddsText_P: str) -> Optional[float]:
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


def _safe_inner_text_sync(El_P, Selector_P: str) -> str:
    return ""


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


def is_player_prop(MarketName_P: str) -> bool:
    Keywords_V = [
        "shots",
        "passes",
        "tackles",
        "assists",
        "to score",
        "shots on target",
        "pass attempts",
        "goalscorer",
        "offsides",
    ]
    name = MarketName_P.lower()
    # Check for player prop keywords
    if any(K_V in name for K_V in Keywords_V):
        return True
    # 'cards' and 'goals' are player props ONLY if they involve a specific player name or 'player' label
    if ("cards" in name or "goals" in name or "goal" in name) and (
        "player" in name or "anytime" in name
    ):
        return True
    return False


def parse_player_prop(SelectionName_P: str, MarketName_P: str):
    # Guarded float(): a malformed line ("X Over abc") must not kill the write loop.
    try:
        Parts_V = SelectionName_P.split(" Over ")
        if len(Parts_V) == 2:
            return Parts_V[0].strip(), MarketName_P, float(Parts_V[1].strip())
        Parts_V = SelectionName_P.split(" Under ")
        if len(Parts_V) == 2:
            return Parts_V[0].strip(), MarketName_P, float(Parts_V[1].strip())
    except (ValueError, TypeError, AttributeError):
        pass
    return None, None, None


def parse_kickertech_events(ApiResponses_P: list) -> dict:
    """
    Parse fixtures from Kickertech/SBTech API responses.
    Returns dict keyed by event_id -> fixture info.
    Handles both camelCase (newer CDL API) and snake_case (older cached API).
    """
    EventsById_V = {}

    for Response_V in ApiResponses_P:
        Data_V = Response_V.get("data") or {}  # guard: json() can return None
        Url_V = Response_V.get("url", "")

        # Only process SBTech domain responses
        if not any(D_V in Url_V for D_V in SBTECH_DOMAINS):
            continue

        if not isinstance(Data_V, dict):
            continue

        # Events can be under 'events' key as a dict keyed by event_id
        RawEvents_V = Data_V.get("events", {})
        if not RawEvents_V:
            continue

        # Convert dict-of-events to list
        if isinstance(RawEvents_V, dict):
            EventList_V = list(RawEvents_V.values())
        elif isinstance(RawEvents_V, list):
            EventList_V = RawEvents_V
        else:
            continue

        for Ev_V in EventList_V:
            if not isinstance(Ev_V, dict):
                continue

            # Support both camelCase and snake_case field names
            EventId_V = Ev_V.get("id")
            if not EventId_V:
                continue

            Teams_V = Ev_V.get("teams", {})
            HomeTeam_V = Teams_V.get("home", "")
            AwayTeam_V = Teams_V.get("away", "")

            # Handle date field naming variants
            DateStart_V = Ev_V.get("dateStart") or Ev_V.get("date_start") or ""
            TournamentName_V = (
                Ev_V.get("tournamentName") or Ev_V.get("tournament_name") or "Football"
            )
            SportId_V = Ev_V.get("sportId") or Ev_V.get("sport_id", 0)

            if HomeTeam_V and AwayTeam_V:
                h = str(HomeTeam_V).lower()
                a = str(AwayTeam_V).lower()
                t = str(TournamentName_V).lower()
                is_women = False
                for kw in [
                    "women",
                    "female",
                    "feminin",
                    "femenil",
                    "femenino",
                    "femminile",
                    "women's",
                ]:
                    if kw in h or kw in a or kw in t:
                        is_women = True
                        break
                if (
                    h.endswith(" (w)")
                    or h.endswith(" w")
                    or a.endswith(" (w)")
                    or a.endswith(" w")
                ):
                    is_women = True

                if is_women:
                    continue

                EventsById_V[str(EventId_V)] = {
                    "fixture_id": str(EventId_V),
                    "home_team": str(HomeTeam_V),
                    "away_team": str(AwayTeam_V),
                    "kickoff_time": str(DateStart_V),
                    "tournament_name": str(TournamentName_V),
                    "sport_id": int(SportId_V),
                    "league_id": str(TournamentName_V),
                }

    logger.info(f"Parsed {len(EventsById_V)} unique events from Kickertech API")
    return EventsById_V


def parse_kickertech_odds(ApiResponses_P: list, EventsById_P: dict) -> dict:
    """
    Parse odds from Kickertech API odds responses.
    Returns dict keyed by event_id -> list of market dicts.
    """
    MarketsByEvent_V = {eid: [] for eid in EventsById_P}

    for Response_V in ApiResponses_P:
        Data_V = Response_V.get("data") or {}  # guard: json() can return None
        Url_V = Response_V.get("url", "")

        if not any(D_V in Url_V for D_V in SBTECH_DOMAINS):
            continue

        if not isinstance(Data_V, dict):
            continue

        # Option A: Parse nested odds from events directly (new format)
        if "events" in Data_V:
            RawEvents_V = Data_V["events"]
            EventList_V = (
                list(RawEvents_V.values())
                if isinstance(RawEvents_V, dict)
                else RawEvents_V
            )
            for Ev_V in EventList_V:
                if not isinstance(Ev_V, dict):
                    continue
                EventId_V = str(Ev_V.get("id"))
                if EventId_V not in MarketsByEvent_V:
                    continue

                MainOdds_V = Ev_V.get("main_odds", {})
                if not isinstance(MainOdds_V, dict):
                    continue

                # 1. Match Result (main)
                main_market = MainOdds_V.get("main")
                if isinstance(main_market, dict):
                    for OddId_V, Odd_V in main_market.items():
                        if not isinstance(Odd_V, dict):
                            continue
                        OddValue_V = Odd_V.get("odd_value")
                        try:
                            OddValue_V = float(OddValue_V)
                        except (TypeError, ValueError):
                            continue
                        OddCode_V = Odd_V.get("odd_code", "")
                        SelectionName_V = Odd_V.get("team_name", Odd_V.get("name", ""))
                        SelectionNorm_V = _normalize_selection(
                            SelectionName_V,
                            OddCode_V,
                            EventsById_P.get(EventId_V, {}),
                            None,
                        )
                        if not any(
                            m["market_id"] == Odd_V.get("unique_id", OddId_V)
                            for m in MarketsByEvent_V[EventId_V]
                        ):
                            MarketsByEvent_V[EventId_V].append(
                                {
                                    "market_id": Odd_V.get("unique_id", OddId_V),
                                    "market_name": "Match Result",
                                    "selection_name": SelectionNorm_V,
                                    "raw_odds": OddValue_V,
                                    "odd_code": OddCode_V,
                                }
                            )

                # 2. Both Teams to Score (bothscore)
                bothscore_market = MainOdds_V.get("bothscore")
                if isinstance(bothscore_market, dict):
                    for OddId_V, Odd_V in bothscore_market.items():
                        if not isinstance(Odd_V, dict):
                            continue
                        OddValue_V = Odd_V.get("odd_value")
                        try:
                            OddValue_V = float(OddValue_V)
                        except (TypeError, ValueError):
                            continue
                        OddCode_V = Odd_V.get("odd_code", "")
                        SelectionName_V = Odd_V.get("team_name", Odd_V.get("name", ""))
                        SelectionNorm_V = _normalize_selection(
                            SelectionName_V,
                            OddCode_V,
                            EventsById_P.get(EventId_V, {}),
                            None,
                        )
                        if not any(
                            m["market_id"] == Odd_V.get("unique_id", OddId_V)
                            for m in MarketsByEvent_V[EventId_V]
                        ):
                            MarketsByEvent_V[EventId_V].append(
                                {
                                    "market_id": Odd_V.get("unique_id", OddId_V),
                                    "market_name": "Both teams to score",
                                    "selection_name": SelectionNorm_V,
                                    "raw_odds": OddValue_V,
                                    "odd_code": OddCode_V,
                                }
                            )

                # 3. Total Goals (total)
                total_market = MainOdds_V.get("total")
                if isinstance(total_market, dict):
                    for OddId_V, Odd_V in total_market.items():
                        if not isinstance(Odd_V, dict):
                            continue
                        OddValue_V = Odd_V.get("odd_value")
                        try:
                            OddValue_V = float(OddValue_V)
                        except (TypeError, ValueError):
                            continue
                        OddCode_V = Odd_V.get("odd_code", "")
                        LineRaw_V = Odd_V.get("additional_value_raw") or Odd_V.get(
                            "additional_value", ""
                        )
                        try:
                            Line_V = float(str(LineRaw_V).strip())
                        except Exception:
                            Line_V = 2.5
                        SelectionName_V = Odd_V.get("team_name", Odd_V.get("name", ""))
                        if (
                            "over" in SelectionName_V.lower()
                            or "ovr" in OddCode_V.lower()
                            or "over" in str(Odd_V.get("name", "")).lower()
                        ):
                            SelectionNorm_V = f"Total OVER {Line_V}"
                        else:
                            SelectionNorm_V = f"Total UNDER {Line_V}"
                        if not any(
                            m["market_id"] == Odd_V.get("unique_id", OddId_V)
                            for m in MarketsByEvent_V[EventId_V]
                        ):
                            MarketsByEvent_V[EventId_V].append(
                                {
                                    "market_id": Odd_V.get("unique_id", OddId_V),
                                    "market_name": "Total Goals",
                                    "selection_name": SelectionNorm_V,
                                    "raw_odds": OddValue_V,
                                    "odd_code": OddCode_V,
                                }
                            )

        # Option B: Odds endpoint returns {"odds": {odd_id: odd_object}} (old format, legacy support)
        RawOdds_V = Data_V.get("odds", {})
        if isinstance(RawOdds_V, dict) and len(RawOdds_V) > 0:
            for OddId_V, Odd_V in RawOdds_V.items():
                if not isinstance(Odd_V, dict):
                    continue

                EventId_V = str(Odd_V.get("eventId", ""))
                if EventId_V not in MarketsByEvent_V:
                    continue

                OddValue_V = Odd_V.get("oddValue")
                try:
                    OddValue_V = float(OddValue_V)
                    if not (1.01 <= OddValue_V <= 100.0):
                        continue
                except (TypeError, ValueError):
                    continue

                MarketName_V = ""
                SelectionName_V = Odd_V.get("name", "")
                OddCode_V = Odd_V.get("oddCode", "")

                MarketName_V = ODD_CODE_MAP.get(OddCode_V, "")
                if not MarketName_V:
                    NameLower_V = SelectionName_V.lower()
                    if "both teams" in NameLower_V:
                        MarketName_V = "Both teams to score"
                    elif "over" in NameLower_V or "under" in NameLower_V:
                        if "corner" in NameLower_V:
                            MarketName_V = "Total Corners"
                        elif "booking" in NameLower_V or "card" in NameLower_V:
                            MarketName_V = "Total Cards"
                        else:
                            MarketName_V = "Total Goals"
                    else:
                        MarketName_V = "Match Result"

                AdditionalValue_V = Odd_V.get("additionalValue", "")
                try:
                    BettingLine_V = (
                        float(str(AdditionalValue_V).strip())
                        if AdditionalValue_V
                        else None
                    )
                except (ValueError, TypeError):
                    BettingLine_V = None

                SelectionNorm_V = _normalize_selection(
                    SelectionName_V,
                    OddCode_V,
                    EventsById_P.get(EventId_V, {}),
                    BettingLine_V,
                )

                MarketId_V = f"{EventId_V}_{OddId_V}"
                exists = any(
                    m["market_id"] == MarketId_V for m in MarketsByEvent_V[EventId_V]
                )
                if not exists:
                    MarketsByEvent_V[EventId_V].append(
                        {
                            "market_id": MarketId_V,
                            "market_name": MarketName_V,
                            "selection_name": SelectionNorm_V,
                            "raw_odds": OddValue_V,
                            "odd_code": OddCode_V,
                        }
                    )

        # Option C: single-pre-event.json (Deep Markets)
        if "single-pre-event.json" in Url_V:
            # logger.info(f"[PARSER] Found deep market file: {Url_V[:100]}")
            EventData_V = Data_V.get("data")
            if not isinstance(EventData_V, dict):
                EventData_V = Data_V  # Fallback if 'data' wrapper is missing

            Groups_V = EventData_V.get("groups", [])
            Info_V = EventData_V.get("info") or {}
            _data_safe = Data_V if isinstance(Data_V, dict) else {}
            EventId_V = str(Info_V.get("id") or _data_safe.get("id", ""))

            if not EventId_V and "lb/" in Url_V:
                import re

                match = re.search(r"lb/(\d+)/", Url_V)
                if match:
                    EventId_V = match.group(1)

            # Ensure EventId_V is a string for lookup
            EventId_V = str(EventId_V) if EventId_V else ""

            if EventId_V and EventId_V in MarketsByEvent_V:
                found_deep = 0

                # C.1: Try groups structure
                for Group_V in Groups_V:
                    for Mkt_V in Group_V.get("markets", []):
                        MarketId_V = str(Mkt_V.get("id"))
                        MarketName_V = Mkt_V.get("name", "")
                        for Selection_V in Mkt_V.get("odds", []):
                            # None/junk value must not abort the whole parse
                            try:
                                SelValue_V = float(Selection_V.get("value", 0))
                            except (TypeError, ValueError):
                                continue
                            UniqueOddId_V = f"{EventId_V}_{Selection_V.get('id')}"
                            if not any(
                                m["market_id"] == UniqueOddId_V
                                for m in MarketsByEvent_V[EventId_V]
                            ):
                                # Reuse market name mapping logic
                                MName_V = ODD_CODE_MAP.get(
                                    Selection_V.get("oddCode"), ""
                                )
                                if not MName_V:
                                    MName_V = MarketName_V

                                SelectionNorm_V = _normalize_selection(
                                    Selection_V.get("name", ""),
                                    Selection_V.get("oddCode", ""),
                                    EventsById_P.get(EventId_V, {}),
                                    Selection_V.get("additionalValue"),
                                )
                                MarketsByEvent_V[EventId_V].append(
                                    {
                                        "market_id": UniqueOddId_V,
                                        "market_name": MName_V,
                                        "selection_name": SelectionNorm_V,
                                        "raw_odds": SelValue_V,
                                        "odd_code": Selection_V.get("oddCode", ""),
                                    }
                                )
                                found_deep += 1

                # C.2: Try direct odds structure
                DeepOdds_V = EventData_V.get("odds", {})
                if isinstance(DeepOdds_V, dict) and len(DeepOdds_V) > 0:
                    logger.info(
                        f"[PARSER] Event {EventId_V} has {len(DeepOdds_V)} odds in deep file."
                    )
                    for OddId_V, Odd_V in DeepOdds_V.items():
                        if not isinstance(Odd_V, dict):
                            continue

                        # Support both camelCase and snake_case keys
                        OddValue_V = Odd_V.get("oddValue") or Odd_V.get("odd_value")
                        try:
                            OddValue_V = float(OddValue_V)
                        except (TypeError, ValueError):
                            continue

                        SelectionName_V = (
                            Odd_V.get("name") or Odd_V.get("team_name") or ""
                        )
                        OddCode_V = Odd_V.get("oddCode") or Odd_V.get("odd_code") or ""
                        AdditionalValue_V = (
                            Odd_V.get("additionalValue")
                            or Odd_V.get("additional_value")
                            or Odd_V.get("additional_value_raw")
                        )

                        MName_V = ODD_CODE_MAP.get(OddCode_V, "")
                        if not MName_V:
                            # Map by prefix of odd_code for player props
                            code_upper = OddCode_V.upper()
                            if code_upper.startswith("ODD_PLR_SHOTSONTARGET"):
                                MName_V = "Player Shots on Target"
                            elif code_upper.startswith("ODD_PLR_SHOTS"):
                                MName_V = "Player Shots"
                            elif code_upper.startswith("ODD_SPLR_GOALASSIST"):
                                MName_V = "Player Assists"
                            elif code_upper.startswith("ODD_SPLR_SCORES"):
                                MName_V = "Player Anytime Goalscorer"
                            elif code_upper.startswith(
                                "ODD_SPLR_CARDED"
                            ) or code_upper.startswith("ODD_SPLR_YELLOWCARDED"):
                                MName_V = "Player Cards"
                            elif code_upper.startswith("ODD_PLR_OFFSIDES"):
                                MName_V = "Player Offsides"
                            else:
                                NameLower_V = SelectionName_V.lower()
                                MarketLabel_V = (
                                    Odd_V.get("marketName")
                                    or Odd_V.get("market_name")
                                    or ""
                                ).lower()
                                if (
                                    "both teams" in NameLower_V
                                    or "both teams" in MarketLabel_V
                                ):
                                    MName_V = "Both teams to score"
                                elif (
                                    "corner" in NameLower_V or "corner" in MarketLabel_V
                                ):
                                    MName_V = "Total Corners"
                                elif (
                                    "booking" in NameLower_V
                                    or "card" in NameLower_V
                                    or "booking" in MarketLabel_V
                                    or "card" in MarketLabel_V
                                ):
                                    MName_V = "Total Cards"
                                elif "over" in NameLower_V or "under" in NameLower_V:
                                    MName_V = "Total Goals"
                                else:
                                    MName_V = "Match Result"

                        # If this is a player prop and we have team_player_1_name, format the selection name correctly
                        PlayerName_V = None
                        if isinstance(Odd_V.get("team_player_1_name"), dict):
                            PlayerName_V = Odd_V["team_player_1_name"].get("en")

                        if PlayerName_V and any(
                            kw in MName_V.lower()
                            for kw in [
                                "shots",
                                "assists",
                                "goalscorer",
                                "cards",
                                "offsides",
                            ]
                        ):
                            # Determine over/under and line
                            # E.g. default line is 0.5 for binary props, or use AdditionalValue_V
                            try:
                                LineVal_V = (
                                    float(AdditionalValue_V)
                                    if AdditionalValue_V is not None
                                    else 0.5
                                )
                            except (ValueError, TypeError):
                                LineVal_V = 0.5

                            # Casing check for "over" or "under"
                            is_under = (
                                "under" in SelectionName_V.lower()
                                or "und" in OddCode_V.lower()
                                or "under" in str(Odd_V.get("ttl", "")).lower()
                            )
                            dir_str = "Under" if is_under else "Over"
                            SelectionNorm_V = f"{PlayerName_V} {dir_str} {LineVal_V}"
                        else:
                            SelectionNorm_V = _normalize_selection(
                                SelectionName_V,
                                OddCode_V,
                                EventsById_P.get(EventId_V, {}),
                                AdditionalValue_V,
                            )

                        UniqueOddId_V = f"{EventId_V}_{OddId_V}"
                        if not any(
                            m["market_id"] == UniqueOddId_V
                            for m in MarketsByEvent_V[EventId_V]
                        ):
                            MarketsByEvent_V[EventId_V].append(
                                {
                                    "market_id": UniqueOddId_V,
                                    "market_name": MName_V,
                                    "selection_name": SelectionNorm_V,
                                    "raw_odds": OddValue_V,
                                    "odd_code": OddCode_V,
                                }
                            )
                            found_deep += 1
                else:
                    logger.warning(
                        f"[PARSER] Event {EventId_V} has NO 'odds' dict in deep file. Type: {type(DeepOdds_V)}"
                    )

                if found_deep > 0:
                    logger.info(
                        f"[PARSER] Extracted {found_deep} deep markets for Event {EventId_V}. Total now: {len(MarketsByEvent_V[EventId_V])}"
                    )

    # Final summary log
    total_m = sum(len(v) for v in MarketsByEvent_V.values())
    logger.info(
        f"[PARSER] Finished parsing. Total markets across all events: {total_m}"
    )
    return MarketsByEvent_V


def _normalize_selection(
    SelectionName_P: str,
    OddCode_P: str,
    Fixture_P: dict,
    BettingLine_P: Optional[float] = None,
) -> str:
    """
    Normalize selection names to match what single_bet_predictor.py expects.
    E.g. 'Both teams to score - YES', 'Total OVER 2.5', 'Total UNDER 2.5', 'Spain'
    """
    Code_V = OddCode_P.upper()
    Name_V = SelectionName_P.strip()

    # Both teams to score
    if "BOTHTEAMSSCORE_YES" in Code_V:
        return "Both teams to score - YES"
    if "BOTHTEAMSSCORE_NO" in Code_V:
        return "Both teams to score - NO"

    # Total goals over/under — use explicit additionalValue line if available
    if "TOTALS_OVER" in Code_V:
        if BettingLine_P is not None:
            return f"Total OVER {BettingLine_P}"
        # Fallback: extract line from name like "Over 2.5"
        try:
            Parts_V = Name_V.lower().replace("over", "").strip()
            Line_V = float(Parts_V)
            return f"Total OVER {Line_V}"
        except Exception:
            return "Total OVER"

    if "TOTALS_UNDER" in Code_V:
        if BettingLine_P is not None:
            return f"Total UNDER {BettingLine_P}"
        try:
            Parts_V = Name_V.lower().replace("under", "").strip()
            Line_V = float(Parts_V)
            return f"Total UNDER {Line_V}"
        except Exception:
            return "Total UNDER"

    # Total Goals (alternative code ODD_TTL_1_OVR)
    if "TTL_1_OVR" in Code_V:
        if BettingLine_P is not None:
            return f"Total OVER {BettingLine_P}"
        try:
            Line_V = float(
                Name_V.lower().replace("total over", "").replace("over", "").strip()
            )
            return f"Total OVER {Line_V}"
        except Exception:
            return "Total OVER"
    if "TTL_1_UND" in Code_V:
        if BettingLine_P is not None:
            return f"Total UNDER {BettingLine_P}"
        try:
            Line_V = float(
                Name_V.lower().replace("total under", "").replace("under", "").strip()
            )
            return f"Total UNDER {Line_V}"
        except Exception:
            return "Total UNDER"

    # Corners total over/under — real API code is ODD_CRN_TTL_OVR (embed line)
    if "CRN_TTL_OVR" in Code_V or "CORNER_TTL_OVR" in Code_V:
        if BettingLine_P is not None:
            return f"Corners OVER {BettingLine_P}"
        try:
            Line_V = float(
                Name_V.lower()
                .replace("corners total over", "")
                .replace("over", "")
                .replace("corners", "")
                .strip()
            )
            return f"Corners OVER {Line_V}"
        except Exception:
            return "Corners OVER"
    if "CRN_TTL_UND" in Code_V or "CORNER_TTL_UND" in Code_V:
        if BettingLine_P is not None:
            return f"Corners UNDER {BettingLine_P}"
        try:
            Line_V = float(
                Name_V.lower()
                .replace("corners total under", "")
                .replace("under", "")
                .replace("corners", "")
                .strip()
            )
            return f"Corners UNDER {Line_V}"
        except Exception:
            return "Corners UNDER"

    # Total Shots on Target (ODD_SFG_TTL_OVR — embed line)
    if "SFG_TTL_OVR" in Code_V:
        if BettingLine_P is not None:
            return f"Shots on Target OVER {BettingLine_P}"
        return "Shots on Target OVER"

    # Yellow cards / total cards over/under — embed the line value
    if "YEL_TTL_OVR" in Code_V or "CARD_TTL_OVR" in Code_V:
        if BettingLine_P is not None:
            return f"Cards OVER {BettingLine_P}"
        try:
            Line_V = float(
                Name_V.lower()
                .replace("yellow cards total over", "")
                .replace("cards total over", "")
                .replace("over", "")
                .strip()
            )
            return f"Cards OVER {Line_V}"
        except Exception:
            return "Cards OVER"
    if "YEL_TTL_UND" in Code_V or "CARD_TTL_UND" in Code_V:
        if BettingLine_P is not None:
            return f"Cards UNDER {BettingLine_P}"
        try:
            Line_V = float(
                Name_V.lower()
                .replace("yellow cards total under", "")
                .replace("cards total under", "")
                .replace("under", "")
                .strip()
            )
            return f"Cards UNDER {Line_V}"
        except Exception:
            return "Cards UNDER"

    # 1X2 match result — map codes to team names
    if "1X2_HOME" in Code_V:
        return Fixture_P.get("home_team", Name_V)
    if "1X2_AWAY" in Code_V:
        return Fixture_P.get("away_team", Name_V)
    if "1X2_DRAW" in Code_V:
        return "X"

    # Double chance
    if "DC_1X" in Code_V:
        return f"{Fixture_P.get('home_team', '1')} or Draw"
    if "DC_X2" in Code_V:
        return f"Draw or {Fixture_P.get('away_team', '2')}"
    if "DC_12" in Code_V:
        return f"{Fixture_P.get('home_team', '1')} or {Fixture_P.get('away_team', '2')}"

    return Name_V


def filter_todays_fixtures(EventsById_P: dict, DaysAhead_P: int = 0) -> dict:
    """
    Filter events to only those kicking off on today's date (UTC) or within DaysAhead days.
    Returns filtered dict.
    """
    Now_V = datetime.datetime.now(datetime.timezone.utc)
    TargetDates_V = set()
    for DayOffset_V in range(DaysAhead_P + 1):
        TargetDate_V = (Now_V + datetime.timedelta(days=DayOffset_V)).strftime(
            "%Y-%m-%d"
        )
        TargetDates_V.add(TargetDate_V)

    Filtered_V = {}
    for EventId_V, Fix_V in EventsById_P.items():
        KickoffStr_V = Fix_V.get("kickoff_time", "")
        if not KickoffStr_V:
            continue
        try:
            # Parse ISO format kickoff time
            KickoffDt_V = datetime.datetime.fromisoformat(
                KickoffStr_V.replace("Z", "+00:00")
            )
            KickoffDate_V = KickoffDt_V.strftime("%Y-%m-%d")
            if KickoffDate_V in TargetDates_V:
                Fix_V["kickoff_date"] = KickoffDate_V
                Filtered_V[EventId_V] = Fix_V
        except Exception:
            continue

    logger.info(
        f"Filtered to {len(Filtered_V)} fixtures for dates {sorted(TargetDates_V)}"
    )
    return Filtered_V


async def run_full_probe(Page_P) -> None:
    """Save page HTML + screenshot for debugging."""
    FullHtml_V = await Page_P.content()
    with open(PROBE_PATH, "w", encoding="utf-8") as F_V:
        F_V.write(FullHtml_V)
    await Page_P.screenshot(path=SCREENSHOT_PATH, full_page=True)
    logger.info(f"Full HTML → {PROBE_PATH} | Screenshot → {SCREENSHOT_PATH}")


async def scrape_fixture_list_html(Page_P) -> list:
    """HTML fallback: scrape fixture list from rendered page."""
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
                h = HomeTeam_V.lower()
                a = AwayTeam_V.lower()
                is_women = False
                for kw in [
                    "women",
                    "female",
                    "feminin",
                    "femenil",
                    "femenino",
                    "femminile",
                    "women's",
                ]:
                    if kw in h or kw in a:
                        is_women = True
                        break
                if (
                    h.endswith(" (w)")
                    or h.endswith(" w")
                    or a.endswith(" (w)")
                    or a.endswith(" w")
                ):
                    is_women = True

                if is_women:
                    continue

                FixtureId_V = f"{HomeTeam_V.strip().lower().replace(' ', '_')}_vs_{AwayTeam_V.strip().lower().replace(' ', '_')}"
                Now_V = datetime.datetime.now(datetime.timezone.utc)
                TodayStr_V = Now_V.strftime("%Y-%m-%d")
                Fixtures_V.append(
                    {
                        "fixture_id": FixtureId_V,
                        "home_team": HomeTeam_V.strip(),
                        "away_team": AwayTeam_V.strip(),
                        "kickoff_time": (
                            KickoffTime_V.strip() if KickoffTime_V else "TBD"
                        ),
                        "kickoff_date": TodayStr_V,
                        "league_id": "FOOTBALL",
                        "tournament_name": "Football",
                    }
                )
        except Exception as E_V:
            logger.warning(f"Failed to parse fixture element: {E_V}")
            continue

    return Fixtures_V


async def run_scraper():
    """Main scraper entry point."""
    init_db()
    try:
        purge_old_data()  # drop long-finished fixtures (safe; bounds DB + kills stale dupes)
    except Exception as PurgeErr_V:
        # Maintenance only — a locked DB here must not kill the scrape run
        logger.warning(f"purge_old_data failed (continuing): {PurgeErr_V}")

    TodayStr_V = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    # NOTE: today's data is cleared AFTER a successful scrape (just before the write
    # loop below), never up front. Clearing first wiped all of today's odds whenever a
    # scrape failed / was killed before finishing — the root cause of the stale-odds bug.

    Conn_V = sqlite3.connect(DB_PATH)
    Cursor_V = Conn_V.cursor()

    FixturesScraped_V = 0
    MarketsScraped_V = 0
    PlayerPropsFound_V = 0

    ApiResponses_V = _ResponseStore()

    async with async_playwright() as p:
        # Lean launch: this scraper only reads intercepted JSON + (as a fallback)
        # the raw DOM text — it never needs images/fonts/media rendered, so
        # blocking them cuts Chromium's RAM/CPU footprint substantially with
        # zero effect on what gets captured.
        browser = await p.chromium.launch(
            headless=HEADLESS_MODE,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--mute-audio",
                "--blink-settings=imagesEnabled=false",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        await context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font", "stylesheet")
            else route.continue_(),
        )
        page = await context.new_page()

        # ── Intercept ALL JSON API responses ────────────────────────────────
        async def handle_response(Response_P):
            Url_V = Response_P.url
            ContentType_V = Response_P.headers.get("content-type", "")
            # Capture JSON from both betarabia and websbkt (Kickertech) APIs
            if "json" in ContentType_V:
                try:
                    JsonData_V = await Response_P.json()
                    # Only parseable payloads are retained, deduped by URL —
                    # the 50 event navigations otherwise stack ~50 copies of
                    # boilerplate nobody reads (see _ResponseStore).
                    if ApiResponses_V.add(Url_V, JsonData_V):
                        logger.info(f"[KT API] Captured: {Url_V[:90]}")
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            # ── Step 1: Navigate directly to Kickertech sports page ──────────
            logger.info("Navigating to betarabia.com/en/sports/kickertech/football ...")
            await page.goto(
                "https://www.betarabia.com/en/sports/kickertech/football",
                wait_until="domcontentloaded",
                timeout=35000,
            )

            # Wait for JS framework to mount
            try:
                await page.wait_for_function(
                    "document.body && document.body.children.length > 2", timeout=15000
                )
            except Exception:
                pass

            # Extra wait for API calls to complete
            await asyncio.sleep(6)

            # Scroll to trigger lazy-loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(2)

            # Accept cookies if banner appears
            try:
                CookieBtn_V = await page.query_selector(
                    "button[id*='accept'], button[class*='accept'], button[class*='cookie']"
                )
                if CookieBtn_V:
                    await CookieBtn_V.click()
                    await random_delay()
            except Exception:
                pass

            # ── Step 2: Navigate to today's football section ─────────────────
            logger.info("Navigating to today's prematch football view ...")
            try:
                await page.goto(
                    "https://www.betarabia.com/en/sports/kickertech/football/today",
                    wait_until="domcontentloaded",
                    timeout=25000,
                )
                await asyncio.sleep(5)
            except Exception:
                logger.warning(
                    "today sub-path not available, continuing with main page data"
                )

            # ── Step 2.5: Visit individual event pages for FULL markets ──────
            # This captures corners, cards, and player props
            temp_events = parse_kickertech_events(ApiResponses_V.as_list())
            today_event_ids = list(
                filter_todays_fixtures(temp_events, DAYS_AHEAD).keys()
            )

            logger.info(
                f"Found {len(today_event_ids)} events for today. Fetching full markets for top 50..."
            )
            # Limiting to 50 for performance
            DeepCaptured_V = 0
            for Idx_V, eid in enumerate(today_event_ids[:50]):
                try:
                    # Recycle the page every _PAGE_RECYCLE_EVERY navigations. Driving
                    # one page through 50 same-origin SPA loads grew the renderer to
                    # 1.34 GB — the JS heap plus the response bodies Playwright must
                    # retain while the page lives. A fresh page drops both.
                    if Idx_V and Idx_V % _PAGE_RECYCLE_EVERY == 0:
                        try:
                            await page.close()
                        except Exception:
                            pass
                        page = await context.new_page()
                        page.on("response", handle_response)
                        logger.info(
                            f"[MEM] Recycled scraper page after {Idx_V} events "
                            f"({len(ApiResponses_V)} payloads retained)"
                        )

                    logger.info(f"Scouting full markets: event {eid}")
                    if await _scout_event(page, eid, ApiResponses_V):
                        DeepCaptured_V += 1
                except Exception as e:
                    logger.warning(f"Failed to fetch event {eid}: {e}")
                    # Short backoff so one bad page doesn't hammer the site
                    await asyncio.sleep(2)
            logger.info(
                f"[DEEP] Captured deep markets for {DeepCaptured_V}/"
                f"{len(today_event_ids[:50])} events"
            )

            # Debug dump of the captured payloads. Off by default: json.dump with
            # indent=2 materialises the whole capture as one string, which on a
            # busy day is hundreds of MB of peak RSS for a file nothing reads.
            # Set BETARABIA_DUMP_API=1 to re-enable when debugging the parsers.
            if os.environ.get("BETARABIA_DUMP_API") == "1":
                try:
                    with open(API_RESPONSES_PATH, "w") as F_V:
                        json.dump(ApiResponses_V.as_list(), F_V)
                    logger.info(
                        f"Saved {len(ApiResponses_V)} API responses → {API_RESPONSES_PATH}"
                    )
                except Exception as DumpErr_V:
                    logger.warning(
                        f"Could not save API responses debug file: {DumpErr_V}"
                    )

            # ── Step 3: Parse Kickertech API events + odds ───────────────────
            AllEventsById_V = parse_kickertech_events(ApiResponses_V.as_list())
            AllOddsByEvent_V = parse_kickertech_odds(
                ApiResponses_V.as_list(), AllEventsById_V
            )

            # Filter to today (+ DAYS_AHEAD)
            TodayEvents_V = filter_todays_fixtures(AllEventsById_V, DAYS_AHEAD)

            if not TodayEvents_V:
                logger.warning(
                    "No Kickertech API events found for today. "
                    "Falling back to ALL events (unfiltered)..."
                )
                TodayEvents_V = AllEventsById_V
                # Add kickoff_date best-effort
                for Fix_V in TodayEvents_V.values():
                    Fix_V["kickoff_date"] = TodayStr_V

            if not TodayEvents_V:
                logger.warning(
                    "Zero events from API. Running HTML probe for debugging..."
                )
                await run_full_probe(page)
                HtmlFixtures_V = await scrape_fixture_list_html(page)
                logger.info(f"HTML fallback found {len(HtmlFixtures_V)} fixtures")
                for Fix_V in HtmlFixtures_V:
                    TodayEvents_V[Fix_V["fixture_id"]] = Fix_V
                    AllOddsByEvent_V[Fix_V["fixture_id"]] = []

            # ── Step 4: Upsert fixtures + markets to DB ──────────────────────
            ScrapedAt_V = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Only NOW, with fresh data in hand, replace today's old rows. If the scrape
            # had failed or been killed before reaching here, the existing odds stay
            # intact instead of being wiped (this is the stale-odds fix).
            if TodayEvents_V:
                clear_todays_data(TodayStr_V)

            for EventId_V, Fix_V in TodayEvents_V.items():
                # Only store football (sport_id=2) or generic fixture from HTML fallback
                SportId_V = Fix_V.get("sport_id", 2)
                if SportId_V not in (2, 0):  # 2=football, 0=HTML fallback
                    continue

                KickoffDate_V = Fix_V.get("kickoff_date", TodayStr_V)
                Cursor_V.execute(
                    """
                    INSERT OR REPLACE INTO fixture
                      (fixture_id, home_team, away_team, kickoff_time, kickoff_date,
                       league_id, tournament_name, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        Fix_V["fixture_id"],
                        Fix_V["home_team"],
                        Fix_V["away_team"],
                        Fix_V["kickoff_time"],
                        KickoffDate_V,
                        Fix_V.get("league_id", "FOOTBALL"),
                        Fix_V.get("tournament_name", "Football"),
                        ScrapedAt_V,
                    ),
                )
                FixturesScraped_V += 1

                # Insert markets for this event
                Markets_V = AllOddsByEvent_V.get(EventId_V, [])
                for Mkt_V in Markets_V:
                    PlayerName_V, PropType_V, Line_V = None, None, None
                    if is_player_prop(Mkt_V["market_name"]):
                        PlayerName_V, PropType_V, Line_V = parse_player_prop(
                            Mkt_V["selection_name"], Mkt_V["market_name"]
                        )
                        if PlayerName_V:
                            PlayerPropsFound_V += 1
                    elif Mkt_V["market_name"] in (
                        "Total Corners",
                        "Total Yellow Cards",
                        "Total Cards",
                    ):
                        # Extract line from selection_name (e.g. "Corners OVER 9.5" → 9.5)
                        import re as _re

                        _m = _re.search(r"(\d+\.?\d*)\s*$", Mkt_V["selection_name"])
                        if _m:
                            try:
                                Line_V = float(_m.group(1))
                            except ValueError:
                                pass

                    Cursor_V.execute(
                        """
                        INSERT OR REPLACE INTO market
                          (market_id, fixture_id, market_name, selection_name,
                           raw_odds, prop_player, prop_type, prop_line, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            Mkt_V["market_id"],
                            EventId_V,
                            Mkt_V["market_name"],
                            Mkt_V["selection_name"],
                            Mkt_V["raw_odds"],
                            PlayerName_V,
                            PropType_V,
                            Line_V,
                            ScrapedAt_V,
                        ),
                    )
                    MarketsScraped_V += 1

        except Exception as MainErr_V:
            import traceback

            traceback.print_exc()
            with open(ERROR_LOG_PATH, "a") as F_V:
                F_V.write(
                    f"[{datetime.datetime.now(datetime.timezone.utc).isoformat()}] "
                    f"Main scraper error: {MainErr_V}\n"
                )
            logger.error(f"Main scraper error: {MainErr_V}")
        finally:
            # Guarded: a dead/hung browser must not prevent the DB commit below
            try:
                await browser.close()
            except Exception as CloseErr_V:
                logger.warning(f"Browser close failed (continuing): {CloseErr_V}")
            Conn_V.commit()
            Conn_V.close()

    print("\n--- SCRAPER HEALTH CHECK ---")
    print(
        f"Target date(s)         : {TodayStr_V}{f' +{DAYS_AHEAD}d' if DAYS_AHEAD else ''}"
    )
    print(f"Total API responses    : {len(ApiResponses_V)}")
    print(f"Fixtures scraped       : {FixturesScraped_V}")
    print(f"Markets scraped        : {MarketsScraped_V}")
    print(f"Player props found     : {PlayerPropsFound_V}")
    print("----------------------------\n")


if __name__ == "__main__":
    asyncio.run(run_scraper())
