"""
crowd_bets_scraper.py
=====================
Paper-bets every prediction from every free crowd/tipster source across all
available markets. Pure research data collection — no real money ever.

Sources
-------
CROWD_SF_ODDS  — Sofascore bookmaker odds (all markets: 1X2, DC, DNB, HT 1X2,
                  BTTS, O/U 0.5-6.5, AH, Cards, Corners, 1st to Score)
CROWD_SF_VOTES — Sofascore crowd votes (1X2 + BTTS + 1st to Score)
CROWD_FB       — Forebet.com predictions (1X2, O/U 2.5, BTTS, Correct Score)
CROWD_FS       — FootyStats.org (BTTS %, O/U %, Corners, Cards stats)
CROWD_WDW      — Windrawwin.com (1X2, O/U 2.5, BTTS)

Staking
-------
stake = settings["crowd_base_stake"] * (confidence_pct / 100)
confidence = de-vigged implied prob (odds sources) or crowd % (vote/tipster sources)

Dedup
-----
One OPEN bet per fixture_id × market_type × side × bet_source — re-runs skip.

Public API
----------
place_crowd_paper_bets(fixtures, page=None)   — call once per daemon cycle
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from fractions import Fraction
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frac_to_decimal(frac: str) -> Optional[float]:
    """'29/100' → 1.29,  '4/1' → 5.0"""
    try:
        f = Fraction(frac)
        return float(f) + 1.0
    except Exception:
        try:
            n, d = frac.split("/")
            return float(n) / float(d) + 1.0
        except Exception:
            return None


def _devig(raw_probs: list[float]) -> list[float]:
    """Strip bookmaker margin so probs sum to 1."""
    total = sum(raw_probs)
    return [p / total for p in raw_probs] if total > 0 else raw_probs


def _implied(decimal_odds: float) -> float:
    """Implied probability from decimal odds."""
    return 1.0 / decimal_odds if decimal_odds and decimal_odds > 1.0 else 0.0


def _load_settings() -> dict:
    path = os.path.join(DATA_DIR, "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _norm(name: str) -> str:
    """Lowercase, strip accents roughly, remove punctuation for fuzzy match."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return name.strip()


def _match_team(target: str, candidates: list[str]) -> Optional[str]:
    """Return the candidate that best fuzzy-matches target, or None."""
    t = _norm(target)
    for c in candidates:
        if _norm(c) == t:
            return c
    # prefix or substring match
    for c in candidates:
        cn = _norm(c)
        if t in cn or cn in t:
            return c
    return None


# ---------------------------------------------------------------------------
# Sofascore Odds Source  (reuses existing patchright page)
# ---------------------------------------------------------------------------

def _sf_odds_for_fixtures(page, fixture_ids: list[int]) -> dict[int, list[dict]]:
    """
    Fetch /api/v1/event/{id}/odds/1/all for each fixture via Promise.all.
    Returns {fixture_id: [market_dict, ...]}
    """
    if not fixture_ids:
        return {}
    calls = ", ".join(
        f"fetch('/api/v1/event/{fid}/odds/1/all',{{headers:{{Accept:'application/json'}}}}).then(r=>r.ok?r.json():null).catch(()=>null)"
        for fid in fixture_ids
    )
    try:
        results = page.evaluate(f"async () => {{ return await Promise.all([{calls}]); }}")
    except Exception as e:
        log.warning(f"[CROWD_SF_ODDS] batch fetch failed: {e}")
        return {}

    out = {}
    for fid, res in zip(fixture_ids, results or []):
        if res and "markets" in res:
            out[fid] = res["markets"]
    return out


def _sf_votes_for_fixtures(page, fixture_ids: list[int]) -> dict[int, dict]:
    """
    Fetch /api/v1/event/{id}/votes for each fixture via Promise.all.
    Returns {fixture_id: vote_dict}
    """
    if not fixture_ids:
        return {}
    calls = ", ".join(
        f"fetch('/api/v1/event/{fid}/votes',{{headers:{{Accept:'application/json'}}}}).then(r=>r.ok?r.json():null).catch(()=>null)"
        for fid in fixture_ids
    )
    try:
        results = page.evaluate(f"async () => {{ return await Promise.all([{calls}]); }}")
    except Exception as e:
        log.warning(f"[CROWD_SF_VOTES] batch fetch failed: {e}")
        return {}

    out = {}
    for fid, res in zip(fixture_ids, results or []):
        if res:
            out[fid] = res
    return out


def _parse_sf_odds_markets(markets: list[dict]) -> list[tuple[str, str, float, float]]:
    """
    Parse Sofascore odds markets into (market_type, selection, decimal_odds, confidence_pct) tuples.
    confidence_pct = de-vigged implied probability × 100.
    """
    picks = []
    for m in markets:
        mg = m.get("marketGroup", "")
        mn = m.get("marketName", "")
        line = m.get("choiceGroup", "")  # e.g. "2.5" for O/U lines
        choices = m.get("choices", [])

        # Determine market_type label
        if mg == "1X2" and "half" not in mn.lower():
            mtype = "1X2"
        elif mg == "1X2" and "half" in mn.lower():
            mtype = "1X2 HT"
        elif mg in ("Double chance", "Double Chance"):
            mtype = "Double Chance"
        elif mg in ("Draw no bet", "Draw No Bet"):
            mtype = "Draw No Bet"
        elif mg in ("Both teams to score",):
            mtype = "BTTS"
        elif mg == "Match goals":
            mtype = f"Over/Under {line}" if line else "Over/Under 2.5"
        elif mg == "Asian Handicap":
            mtype = "Asian Handicap"
        elif mg == "Total Cards":
            mtype = f"Total Cards {line}" if line else "Total Cards"
        elif mg in ("Corners 2-Way", "Corners"):
            mtype = f"Corners {line}" if line else "Corners"
        elif mg == "First team to score":
            mtype = "1st Team to Score"
        elif mg == "Correct score":
            mtype = "Correct Score"
        else:
            mtype = mg or mn

        # Compute de-vigged probs
        decimals = []
        for ch in choices:
            fv = ch.get("fractionalValue") or ch.get("initialFractionalValue") or ""
            dec = _frac_to_decimal(fv)
            decimals.append(dec)

        raw_probs = [_implied(d) for d in decimals if d]
        if len(raw_probs) != len(choices):
            continue
        devigged = _devig(raw_probs)

        for ch, dec, conf in zip(choices, decimals, devigged):
            if dec and dec > 1.0:
                picks.append((mtype, ch["name"], dec, round(conf * 100, 1)))

    return picks


def _parse_sf_votes(vote_data: dict) -> list[tuple[str, str, float, float]]:
    """
    Parse Sofascore crowd votes into (market_type, selection, odds, confidence_pct).
    odds is None (no market odds from votes) → use 2.0 as placeholder.
    """
    picks = []

    vote = vote_data.get("vote") or {}
    v1 = vote.get("vote1", 0)
    vx = vote.get("voteX", 0)
    v2 = vote.get("vote2", 0)
    total_1x2 = v1 + vx + v2
    if total_1x2 > 0:
        picks.append(("1X2", "1", 2.0, round(v1 / total_1x2 * 100, 1)))
        picks.append(("1X2", "X", 2.0, round(vx / total_1x2 * 100, 1)))
        picks.append(("1X2", "2", 2.0, round(v2 / total_1x2 * 100, 1)))

    btts = vote_data.get("bothTeamsToScoreVote") or {}
    by = btts.get("voteYes", 0)
    bn = btts.get("voteNo", 0)
    total_btts = by + bn
    if total_btts > 0:
        picks.append(("BTTS", "Yes", 2.0, round(by / total_btts * 100, 1)))
        picks.append(("BTTS", "No", 2.0, round(bn / total_btts * 100, 1)))

    ftts = vote_data.get("firstTeamToScoreVote") or {}
    fh = ftts.get("voteHome", 0)
    fn = ftts.get("voteNoGoal", 0)
    fa = ftts.get("voteAway", 0)
    total_ftts = fh + fn + fa
    if total_ftts > 0:
        picks.append(("1st Team to Score", "Home", 2.0, round(fh / total_ftts * 100, 1)))
        picks.append(("1st Team to Score", "No Goal", 2.0, round(fn / total_ftts * 100, 1)))
        picks.append(("1st Team to Score", "Away", 2.0, round(fa / total_ftts * 100, 1)))

    return picks


# ---------------------------------------------------------------------------
# Forebet Source
# ---------------------------------------------------------------------------

_FOREBET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

def _scrape_forebet(home_team: str, away_team: str) -> list[tuple[str, str, float, float]]:
    """
    Scrape Forebet for a single match. Returns list of (market, selection, odds, confidence_pct).
    Uses requests + BeautifulSoup — Forebet allows plain HTTP.
    """
    picks = []
    try:
        url = "https://www.forebet.com/en/football-tips-and-predictions-for-today"
        resp = requests.get(url, headers=_FOREBET_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        for row in soup.select("div.rcnt, tr.tr_0, tr.tr_1, .schema"):
            # Try to find team names in the row
            teams_el = row.select(".homeTeam, .awayTeam, .tm_name, .ht, .at")
            if len(teams_el) < 2:
                continue
            h = teams_el[0].get_text(strip=True)
            a = teams_el[1].get_text(strip=True)
            if not (_match_team(home_team, [h]) and _match_team(away_team, [a])):
                continue

            # 1X2 percentages
            pcts = row.select(".l_sh, .percentage, .probs span, .l_sh1, .l_shx, .l_sh2")
            if len(pcts) >= 3:
                try:
                    p1 = float(pcts[0].get_text(strip=True).replace("%", ""))
                    px = float(pcts[1].get_text(strip=True).replace("%", ""))
                    p2 = float(pcts[2].get_text(strip=True).replace("%", ""))
                    picks.extend([
                        ("1X2", "1", 2.0, p1),
                        ("1X2", "X", 2.0, px),
                        ("1X2", "2", 2.0, p2),
                    ])
                except (ValueError, IndexError):
                    pass

            # O/U 2.5 (look for over/under probability element)
            ou_el = row.select_one(".goal_over_25, .ou, .over25")
            if ou_el:
                try:
                    over_pct = float(ou_el.get_text(strip=True).replace("%", ""))
                    picks.extend([
                        ("Over/Under 2.5", "Over", 2.0, over_pct),
                        ("Over/Under 2.5", "Under", 2.0, round(100 - over_pct, 1)),
                    ])
                except ValueError:
                    pass

            # BTTS
            btts_el = row.select_one(".btts, .bts")
            if btts_el:
                try:
                    btts_pct = float(btts_el.get_text(strip=True).replace("%", ""))
                    picks.extend([
                        ("BTTS", "Yes", 2.0, btts_pct),
                        ("BTTS", "No", 2.0, round(100 - btts_pct, 1)),
                    ])
                except ValueError:
                    pass

            if picks:
                break

    except Exception as e:
        log.debug(f"[CROWD_FB] forebet failed for {home_team} vs {away_team}: {e}")
    return picks


def _scrape_forebet_page(home_team: str, away_team: str, page) -> list[tuple[str, str, float, float]]:
    """Forebet via Patchright if requests fails (Cloudflare)."""
    picks = []
    try:
        page.goto("https://www.forebet.com/en/football-tips-and-predictions-for-today",
                  wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        # Use same parsing logic as _scrape_forebet
        for row in soup.select("div.rcnt, .schema, tr"):
            tds = row.select("td, .tm_name")
            texts = [td.get_text(strip=True) for td in tds]
            # Look for the row containing our teams
            row_text = " ".join(texts).lower()
            if _norm(home_team) not in row_text or _norm(away_team) not in row_text:
                continue
            # Extract percentages (3 numbers close together = 1X2)
            nums = re.findall(r'\b(\d{1,3})\s*%', row.get_text())
            if len(nums) >= 3:
                try:
                    p1, px, p2 = float(nums[0]), float(nums[1]), float(nums[2])
                    picks.extend([
                        ("1X2", "1", 2.0, p1),
                        ("1X2", "X", 2.0, px),
                        ("1X2", "2", 2.0, p2),
                    ])
                except (ValueError, IndexError):
                    pass
            break
    except Exception as e:
        log.debug(f"[CROWD_FB] patchright forebet failed: {e}")
    return picks


# ---------------------------------------------------------------------------
# FootyStats Source
# ---------------------------------------------------------------------------

_FS_BASE = "https://footystats.org"

def _scrape_footystats(home_team: str, away_team: str) -> list[tuple[str, str, float, float]]:
    """
    Scrape FootyStats pre-match stats page for a fixture.
    Provides BTTS%, O/U%, Corners avg, Cards avg as probabilities.
    """
    picks = []
    try:
        # Search for the match on FootyStats
        search_url = f"{_FS_BASE}/predictions/today"
        resp = requests.get(search_url, headers=_FOREBET_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        for row in soup.select(".match-row, .prediction-row, tr, .match"):
            text = row.get_text(separator=" ", strip=True).lower()
            if _norm(home_team) not in text or _norm(away_team) not in text:
                continue

            # Extract percentage-style predictions
            stats = row.select(".stat, .percentage, td")
            for stat in stats:
                label = stat.get("data-label", "") or stat.get("class", [""])[0]
                val_text = stat.get_text(strip=True).replace("%", "")
                try:
                    val = float(val_text)
                except (ValueError, TypeError):
                    continue

                label_l = label.lower()
                if "btts" in label_l:
                    picks.extend([
                        ("BTTS", "Yes", 2.0, val),
                        ("BTTS", "No", 2.0, round(100 - val, 1)),
                    ])
                elif "over" in label_l and "2.5" in label_l:
                    picks.extend([
                        ("Over/Under 2.5", "Over", 2.0, val),
                        ("Over/Under 2.5", "Under", 2.0, round(100 - val, 1)),
                    ])
                elif "corner" in label_l:
                    over_pct = min(val, 99.0)
                    picks.extend([
                        ("Corners", "Over", 2.0, over_pct),
                        ("Corners", "Under", 2.0, round(100 - over_pct, 1)),
                    ])
                elif "card" in label_l:
                    over_pct = min(val, 99.0)
                    picks.extend([
                        ("Total Cards", "Over", 2.0, over_pct),
                        ("Total Cards", "Under", 2.0, round(100 - over_pct, 1)),
                    ])
            if picks:
                break
    except Exception as e:
        log.debug(f"[CROWD_FS] footystats failed for {home_team} vs {away_team}: {e}")
    return picks


# ---------------------------------------------------------------------------
# Windrawwin Source
# ---------------------------------------------------------------------------

def _scrape_windrawwin(home_team: str, away_team: str) -> list[tuple[str, str, float, float]]:
    """Scrape Windrawwin for 1X2, O/U 2.5, BTTS percentages."""
    picks = []
    try:
        url = "https://www.windrawwin.com/predictions/future/"
        resp = requests.get(url, headers=_FOREBET_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        for row in soup.select("tr, .match-row"):
            text = row.get_text(separator=" ", strip=True).lower()
            if _norm(home_team) not in text or _norm(away_team) not in text:
                continue

            tds = row.select("td")
            pcts = []
            for td in tds:
                t = td.get_text(strip=True).replace("%", "")
                try:
                    v = float(t)
                    if 0 <= v <= 100:
                        pcts.append(v)
                except ValueError:
                    pass

            # Windrawwin rows typically: [home%, draw%, away%, over%, btts%]
            if len(pcts) >= 3:
                picks.extend([
                    ("1X2", "1", 2.0, pcts[0]),
                    ("1X2", "X", 2.0, pcts[1]),
                    ("1X2", "2", 2.0, pcts[2]),
                ])
            if len(pcts) >= 4:
                picks.extend([
                    ("Over/Under 2.5", "Over", 2.0, pcts[3]),
                    ("Over/Under 2.5", "Under", 2.0, round(100 - pcts[3], 1)),
                ])
            if len(pcts) >= 5:
                picks.extend([
                    ("BTTS", "Yes", 2.0, pcts[4]),
                    ("BTTS", "No", 2.0, round(100 - pcts[4], 1)),
                ])
            if picks:
                break
    except Exception as e:
        log.debug(f"[CROWD_WDW] windrawwin failed for {home_team} vs {away_team}: {e}")
    return picks


# ---------------------------------------------------------------------------
# Paper bet logger
# ---------------------------------------------------------------------------

def _log_crowd_bet(
    match: str,
    market: str,
    selection: str,
    odds: float,
    confidence_pct: float,
    stake: float,
    bet_source: str,
    fixture_id=None,
    league: str = "",
):
    """
    Write one research paper bet directly to bet_log, bypassing bankroll exposure caps.
    Crowd bets are pure research tracking — they don't affect the paper bankroll.
    Dedup: skips if same fixture+market+selection+source already has an OPEN bet.
    """
    import sqlite3
    import datetime
    import hashlib

    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Dedup check
        cur.execute(
            "SELECT COUNT(*) FROM bet_log WHERE match_id=? AND market_type=? AND side=? AND bet_source=? AND result='OPEN'",
            (match, market, selection, bet_source),
        )
        if cur.fetchone()[0] > 0:
            conn.close()
            return

        fid_str = str(fixture_id) if fixture_id else ""
        h = hashlib.md5(f"{bet_source}{match}{market}{selection}".encode()).hexdigest()[:12]
        bet_id = f"{bet_source[:8]}_{h}"

        cur.execute(
            """INSERT OR IGNORE INTO bet_log
               (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake,
                result, pnl, placed_at, bet_source, is_recommended, line, side, fixture_id, league)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bet_id,
                match,
                "",
                market,
                round(max(odds, 1.01), 4),
                round(max(odds, 1.01), 4),
                round(confidence_pct, 2),
                round(stake, 2),
                "OPEN",
                0.0,
                datetime.datetime.now().isoformat(),
                bet_source,
                1,
                "",
                selection,
                fid_str,
                league,
            ),
        )
        conn.commit()
        conn.close()
        log.debug(f"[{bet_source}] {match} | {market} | {selection} @ {odds:.2f} | conf {confidence_pct:.1f}% | stake ${stake:.2f}")
    except Exception as e:
        log.debug(f"[CROWD] log_crowd_bet failed ({bet_source} {match} {market} {selection}): {e}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def place_crowd_paper_bets(fixtures: list[dict], page=None) -> int:
    """
    For each fixture × source × market × selection: log a shadow paper bet.

    `page` is an existing Patchright page already navigated to sofascore.com
    (from sofascore_patchright_scraper). If None, we open our own browser.

    Returns total number of bets placed this run.
    """
    settings = _load_settings()
    # Default OFF: this floods bet_log with every odds/vote selection for every
    # fixture (thousands of rows/day). Enable explicitly for research runs only.
    if not settings.get("crowd_betting_enabled", False):
        return 0

    base_stake = float(settings.get("crowd_base_stake", 25.0))
    total_placed = 0

    # --- Set up Patchright session for Sofascore ---
    own_browser = False
    browser = None
    sf_page = page

    if sf_page is None:
        try:
            from patchright.sync_api import sync_playwright
            _pw = sync_playwright().start()
            browser = _pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            sf_page = ctx.new_page()
            sf_page.goto("https://www.sofascore.com/football", wait_until="domcontentloaded", timeout=30000)
            sf_page.wait_for_timeout(2000)
            own_browser = True
        except Exception as e:
            log.error(f"[CROWD] Failed to launch patchright: {e}")
            return 0

    try:
        # Collect fixture IDs — only those with a real Sofascore ID (< 100M are real)
        sf_fixture_ids = []
        for fx in fixtures:
            fid = fx.get("fixture", {}).get("id")
            if fid and int(fid) < 100_000_000:
                sf_fixture_ids.append(int(fid))

        log.info(f"[CROWD] Processing {len(fixtures)} fixtures ({len(sf_fixture_ids)} with SF IDs)")

        # ── Source 1: Sofascore Odds ──────────────────────────────────────
        log.info("[CROWD] Fetching Sofascore odds...")
        sf_odds = _sf_odds_for_fixtures(sf_page, sf_fixture_ids)
        log.info(f"[CROWD] Got odds for {len(sf_odds)} fixtures")

        for fid, markets in sf_odds.items():
            # Find the fixture dict
            fx_match = next(
                (f for f in fixtures if f.get("fixture", {}).get("id") == fid), None
            )
            if not fx_match:
                continue
            home = fx_match["teams"]["home"]["name"]
            away = fx_match["teams"]["away"]["name"]
            match_name = f"{home} vs {away}"
            league = fx_match.get("league", {}).get("name", "")

            picks = _parse_sf_odds_markets(markets)
            for mtype, selection, odds, conf_pct in picks:
                stake = round(base_stake * conf_pct / 100, 2)
                _log_crowd_bet(match_name, mtype, selection, odds, conf_pct, stake,
                               "CROWD_SF_ODDS", fixture_id=fid, league=league)
                total_placed += 1

        # ── Source 2: Sofascore Votes ─────────────────────────────────────
        log.info("[CROWD] Fetching Sofascore votes...")
        sf_votes = _sf_votes_for_fixtures(sf_page, sf_fixture_ids)
        log.info(f"[CROWD] Got votes for {len(sf_votes)} fixtures")

        for fid, vote_data in sf_votes.items():
            fx_match = next(
                (f for f in fixtures if f.get("fixture", {}).get("id") == fid), None
            )
            if not fx_match:
                continue
            home = fx_match["teams"]["home"]["name"]
            away = fx_match["teams"]["away"]["name"]
            match_name = f"{home} vs {away}"
            league = fx_match.get("league", {}).get("name", "")

            picks = _parse_sf_votes(vote_data)
            for mtype, selection, odds, conf_pct in picks:
                stake = round(base_stake * conf_pct / 100, 2)
                _log_crowd_bet(match_name, mtype, selection, odds, conf_pct, stake,
                               "CROWD_SF_VOTES", fixture_id=fid, league=league)
                total_placed += 1

        # ── Sources 3-5: External tipster sites (per fixture) ─────────────
        # These are slower HTTP scrapes — only run on upcoming fixtures to reduce load
        upcoming = [
            f for f in fixtures
            if f.get("fixture", {}).get("status", {}).get("short", "") == "NS"
        ]
        log.info(f"[CROWD] Scraping external sources for {len(upcoming)} upcoming fixtures...")

        forebet_loaded = False
        forebet_html_cache: Optional[str] = None
        wdw_html_cache: Optional[str] = None

        # Pre-fetch Forebet and Windrawwin pages once
        try:
            resp = requests.get(
                "https://www.forebet.com/en/football-tips-and-predictions-for-today",
                headers=_FOREBET_HEADERS, timeout=15
            )
            if resp.status_code == 200:
                forebet_html_cache = resp.text
                forebet_loaded = True
        except Exception as e:
            log.debug(f"[CROWD_FB] forebet page fetch failed: {e}")

        try:
            resp = requests.get(
                "https://www.windrawwin.com/predictions/future/",
                headers=_FOREBET_HEADERS, timeout=15
            )
            if resp.status_code == 200:
                wdw_html_cache = resp.text
        except Exception as e:
            log.debug(f"[CROWD_WDW] windrawwin page fetch failed: {e}")

        for fx in upcoming[:200]:  # cap at 200 to avoid very long runs
            home = fx["teams"]["home"]["name"]
            away = fx["teams"]["away"]["name"]
            match_name = f"{home} vs {away}"
            league = fx.get("league", {}).get("name", "")
            fid = fx.get("fixture", {}).get("id")

            # Forebet
            if forebet_html_cache:
                fb_picks = _parse_forebet_html(forebet_html_cache, home, away)
                for mtype, selection, odds, conf_pct in fb_picks:
                    stake = round(base_stake * conf_pct / 100, 2)
                    _log_crowd_bet(match_name, mtype, selection, odds, conf_pct, stake,
                                   "CROWD_FB", fixture_id=fid, league=league)
                    total_placed += 1

            # Windrawwin
            if wdw_html_cache:
                wdw_picks = _parse_wdw_html(wdw_html_cache, home, away)
                for mtype, selection, odds, conf_pct in wdw_picks:
                    stake = round(base_stake * conf_pct / 100, 2)
                    _log_crowd_bet(match_name, mtype, selection, odds, conf_pct, stake,
                                   "CROWD_WDW", fixture_id=fid, league=league)
                    total_placed += 1

            # FootyStats
            fs_picks = _scrape_footystats(home, away)
            for mtype, selection, odds, conf_pct in fs_picks:
                stake = round(base_stake * conf_pct / 100, 2)
                _log_crowd_bet(match_name, mtype, selection, odds, conf_pct, stake,
                               "CROWD_FS", fixture_id=fid, league=league)
                total_placed += 1

        log.info(f"[CROWD] Done. Total bets logged this run: {total_placed}")
        return total_placed

    finally:
        if own_browser and browser:
            try:
                browser.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# HTML parsers for cached pages (avoids re-fetching per fixture)
# ---------------------------------------------------------------------------

def _parse_forebet_html(html: str, home_team: str, away_team: str) -> list[tuple]:
    picks = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("div.rcnt, .schema, .tips_area tr"):
            text = row.get_text(separator=" ", strip=True)
            tl = text.lower()
            if _norm(home_team) not in tl or _norm(away_team) not in tl:
                continue
            # Find all percentages
            nums = re.findall(r'(\d{1,3})\s*%', text)
            flt = []
            for n in nums:
                v = float(n)
                if 0 < v <= 100:
                    flt.append(v)
            if len(flt) >= 3:
                picks.extend([
                    ("1X2", "1", 2.0, flt[0]),
                    ("1X2", "X", 2.0, flt[1]),
                    ("1X2", "2", 2.0, flt[2]),
                ])
            # O/U — look for a standalone number that's a goal-count probability
            if len(flt) >= 4:
                picks.extend([
                    ("Over/Under 2.5", "Over", 2.0, flt[3]),
                    ("Over/Under 2.5", "Under", 2.0, round(100 - flt[3], 1)),
                ])
            if picks:
                break
    except Exception as e:
        log.debug(f"[CROWD_FB] parse failed: {e}")
    return picks


def _parse_wdw_html(html: str, home_team: str, away_team: str) -> list[tuple]:
    picks = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("tr, .match-row, .prediction"):
            text = row.get_text(separator=" ", strip=True)
            tl = text.lower()
            if _norm(home_team) not in tl or _norm(away_team) not in tl:
                continue
            nums = re.findall(r'(\d{1,3})%', text)
            flt = [float(n) for n in nums if 0 < float(n) <= 100]
            if len(flt) >= 3:
                picks.extend([
                    ("1X2", "1", 2.0, flt[0]),
                    ("1X2", "X", 2.0, flt[1]),
                    ("1X2", "2", 2.0, flt[2]),
                ])
            if len(flt) >= 4:
                picks.extend([
                    ("Over/Under 2.5", "Over", 2.0, flt[3]),
                    ("Over/Under 2.5", "Under", 2.0, round(100 - flt[3], 1)),
                ])
            if len(flt) >= 5:
                picks.extend([
                    ("BTTS", "Yes", 2.0, flt[4]),
                    ("BTTS", "No", 2.0, round(100 - flt[4], 1)),
                ])
            if picks:
                break
    except Exception as e:
        log.debug(f"[CROWD_WDW] parse failed: {e}")
    return picks


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from src.sofascore_patchright_scraper import get_sofascore_fixtures_today
    print("Fetching today's fixtures...")
    fixtures = get_sofascore_fixtures_today()
    print(f"Got {len(fixtures)} fixtures. Placing crowd paper bets...")
    n = place_crowd_paper_bets(fixtures)
    print(f"Done. {n} bets logged.")
