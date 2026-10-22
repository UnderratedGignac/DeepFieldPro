"""
tipster_scraper.py — Football prediction aggregator
====================================================
Scrapes today's football match predictions from public tipster/model sites
and places paper bets for research and CLV evaluation.

Sources:
  - Forebet   (mathematical model, requests-based)
  - PredictZ  (community tips, Playwright fallback)

Usage:
    from src.tipster_scraper import get_all_tipster_predictions, place_tipster_bets
    preds = get_all_tipster_predictions()
    placed = place_tipster_bets(preds)
"""

import datetime
import hashlib
import logging
import os
import re
import sqlite3
import statistics
import time

import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from src.name_matching import get_match_score

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The disciplined, $200-capped "real" ledger. Only Forebet-confirmed picks
# (the one strategy validated at +41.7% ROI, n=259 — see TOURNAMENT_PLAYBOOK.md)
# are gated against and staked from this bankroll. All other tipster sources
# (PredictZ, SoccerPunter) keep writing to bet_log.db only, ungated, as
# pure research — they are NOT the validated strategy.
REAL_BANKROLL_DB = os.path.join(BASE_DIR, "data", "real_bankroll.db")

_REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─────────────────────────────────────────────
# SOURCE 1 — Forebet (requests-based, works)
# ─────────────────────────────────────────────

def _fetch_forebet(url: str, attempts: int = 3, timeout: int = 20) -> str | None:
    """GET a Forebet page with retry + exponential backoff.

    Per-attempt classification: 403/429 mean blocked/rate-limited (warn),
    other statuses and network errors log and back off. Returns HTML text or
    None after the final attempt so callers degrade to "no picks" — the
    correct fail-safe for a confirmation-required gate (nothing confirmed
    beats confirming on bad data).
    """
    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, headers=_REQ_HEADERS, timeout=timeout)
            if r.status_code == 200 and r.text:
                logger.info(f"[FOREBET] GET {url} -> 200 ({len(r.text)} bytes)")
                return r.text
            log = logger.warning if r.status_code in (403, 429) else logger.info
            log(f"[FOREBET] GET {url} -> HTTP {r.status_code} (attempt {attempt}/{attempts})")
        except Exception as e:
            logger.warning(f"[FOREBET] GET {url} error (attempt {attempt}/{attempts}): {e}")
        if attempt < attempts:
            time.sleep(delay)
            delay *= 2.5
    return None


def get_forebet_predictions(date_str: str | None = None) -> list[dict]:
    """
    Forebet 1X2 predictions for one calendar date: the daily list page
    (today/tomorrow only — Forebet has no daily URL beyond that) MERGED with
    the World Cup competition page.

    The WC page merge is load-bearing: Forebet's daily list pages do NOT
    carry World Cup fixtures at all (root cause of the 2026-07-10 incident
    where every semifinal sat tipster_confirmed=false while forebet.com
    visibly published picks). WC rows are date-filtered by each row's own
    <time datetime> tag — the competition page also lists already-played
    rounds with their old pre-match predictions, and a stale row for a
    repeat pairing must never confirm a future fixture.
    """
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    today = datetime.date.today()
    try:
        delta = (datetime.date.fromisoformat(date_str) - today).days
    except ValueError:
        date_str = today.isoformat()
        delta = 0

    predictions: list[dict] = []

    if delta in (0, 1):
        url = (
            "https://www.forebet.com/en/football-tips-and-predictions-for-today"
            if delta == 0
            else "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow"
        )
        html = _fetch_forebet(url)
        if html:
            predictions = _parse_forebet_daily_html(html, date_str)
    # delta >= 2: no daily page exists. The old code silently served the
    # TODAY page here (wrong day's predictions under a future date label);
    # now only the date-filtered competition rows below can serve far dates.

    seen = {(p["home_team"].lower(), p["away_team"].lower()) for p in predictions}
    for p in get_forebet_wc_predictions(date_str):
        if (p["home_team"].lower(), p["away_team"].lower()) not in seen:
            predictions.append(p)

    logger.info(f"[FOREBET] {date_str}: {len(predictions)} predictions total")
    return predictions


def _parse_forebet_daily_html(html: str, date_str: str) -> list[dict]:
    """Parse a daily list page: every div.rcnt row is that day's match."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("div", class_="rcnt")
    logger.info(f"[FOREBET] daily page: {len(rows)} prediction rows")
    predictions = []
    for row in rows:
        try:
            pred = _parse_forebet_row(row, date_str)
            if pred:
                predictions.append(pred)
        except Exception as e:
            logger.debug(f"[FOREBET] row parse error: {e}")
    return predictions


def _parse_forebet_row(row, date_str: str) -> dict | None:
    # Team names from schema.org metadata
    meta_name = row.find("meta", itemprop="name")
    if not meta_name:
        return None

    match_name = meta_name.get("content", "")
    if " vs " not in match_name:
        return None
    home_team, away_team = match_name.split(" vs ", 1)

    # Probabilities from fprc div — packed as "273836" → 27|38|36
    fprc = row.find("div", class_="fprc")
    prob_home = prob_draw = prob_away = None
    if fprc:
        txt = fprc.get_text(strip=True)
        # Remove non-digit chars and split into 2-char chunks
        digits = re.sub(r"\D", "", txt)
        if len(digits) == 6:
            prob_home = int(digits[0:2])
            prob_draw = int(digits[2:4])
            prob_away = int(digits[4:6])
        elif len(digits) == 5:
            # e.g. "9 38 53" → "93853" — first group is 1 digit
            if digits[1:3].isdigit() and int(digits[1:3]) <= 99:
                prob_home = int(digits[0:1])
                prob_draw = int(digits[1:3])
                prob_away = int(digits[3:5])

    # Predicted side — in the full text the field after probs is X/1/2
    # Look for lay_right or predict divs
    predict_div = row.find("div", class_="lay_right")
    predicted_side = None
    if predict_div:
        raw = predict_div.get_text(strip=True)
        if raw == "1":
            predicted_side = "Home (1)"
        elif raw == "X":
            predicted_side = "Draw (X)"
        elif raw == "2":
            predicted_side = "Away (2)"

    # Fallback: use highest probability
    if predicted_side is None and prob_home is not None:
        maxp = max(prob_home, prob_draw, prob_away)
        if maxp == prob_home:
            predicted_side = "Home (1)"
        elif maxp == prob_draw:
            predicted_side = "Draw (X)"
        else:
            predicted_side = "Away (2)"

    # Average expected goals
    avg_sc_div = row.find("div", class_="avg_sc")
    avg_goals = None
    if avg_sc_div:
        try:
            avg_goals = float(avg_sc_div.get_text(strip=True))
        except ValueError:
            pass

    # O/U prediction from avg_goals
    predicted_ou = None
    if avg_goals is not None:
        predicted_ou = "Over 2.5" if avg_goals >= 2.5 else "Under 2.5"

    if not predicted_side:
        return None

    confidence = max(prob_home or 0, prob_draw or 0, prob_away or 0)

    return {
        "home_team": home_team.strip(),
        "away_team": away_team.strip(),
        "date": date_str,
        "source": "FOREBET",
        "predicted_side": predicted_side,
        "confidence": float(confidence),
        "predicted_ou": predicted_ou,
        "avg_goals": avg_goals,
        "prob_home": prob_home,
        "prob_draw": prob_draw,
        "prob_away": prob_away,
    }


# ─────────────────────────────────────────────
# SOURCE 1b — Forebet World Cup competition page
# ─────────────────────────────────────────────

FOREBET_WC_URL = "https://www.forebet.com/en/predictions-world/world-cup"
_WC_HTML_CACHE: dict = {"ts": 0.0, "html": None, "rows": 0}
_WC_HTML_TTL = 900  # 15 min — page updates slowly; gates poll every few minutes


def get_forebet_wc_predictions(date_str: str) -> list[dict]:
    """World-Cup competition-page predictions for one calendar date.

    The page HTML is cached for _WC_HTML_TTL so the today+tomorrow double
    call the confirmation gates make each cycle costs at most one fetch.
    A failed fetch caches None for the TTL (same fail-safe backoff rationale
    as get_tipster_picks): no data in means nothing gets confirmed.
    """
    now = time.time()
    if now - _WC_HTML_CACHE["ts"] >= _WC_HTML_TTL:
        html = _fetch_forebet(FOREBET_WC_URL)
        _WC_HTML_CACHE["ts"] = now
        _WC_HTML_CACHE["html"] = html
        if html:
            n_rows = len(
                BeautifulSoup(html, "html.parser").find_all("div", class_="rcnt")
            )
            if n_rows == 0 and _WC_HTML_CACHE["rows"] > 0:
                logger.warning(
                    "[FOREBET] WC page fetched OK but has 0 prediction rows "
                    f"(previously {_WC_HTML_CACHE['rows']}) — layout change? "
                    "Confirmations will stall until fixed."
                )
            _WC_HTML_CACHE["rows"] = n_rows
    html = _WC_HTML_CACHE["html"]
    if not html:
        return []
    return _parse_forebet_wc_html(html, date_str)


def _parse_forebet_wc_html(html: str, date_str: str) -> list[dict]:
    """Parse WC competition-page rows, keeping ONLY rows whose own
    <time datetime="YYYY-MM-DD"> equals date_str.

    The page lists played rounds alongside upcoming ones, and played rows
    keep their old pre-match predictions — without this filter a stale row
    (e.g. a group-stage meeting of the same two teams) could confirm a
    future fixture it never predicted.
    """
    soup = BeautifulSoup(html, "html.parser")
    predictions = []
    for row in soup.find_all("div", class_="rcnt"):
        try:
            t = row.find("time")
            row_date = (t.get("datetime") or "").strip()[:10] if t else ""
            if row_date != date_str:
                continue
            pred = _parse_forebet_row(row, date_str)
            if pred:
                predictions.append(pred)
        except Exception as e:
            logger.debug(f"[FOREBET] WC row parse error: {e}")
    return predictions


# ─────────────────────────────────────────────
# SOURCE 2 — PredictZ (Playwright fallback)
# ─────────────────────────────────────────────

def get_predictz_predictions(date_str: str | None = None) -> list[dict]:
    """Fetch predictions from PredictZ using Playwright (site blocks requests)."""
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[PREDICTZ] playwright not installed")
        return []

    predictions = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
            page.goto("https://www.predictz.com/predictions/", timeout=30000)
            page.wait_for_selector("table", timeout=15000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table tr")
        logger.info(f"[PREDICTZ] {len(rows)} table rows")

        for row in rows:
            try:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) < 4:
                    continue
                # PredictZ columns vary; look for rows with team vs team pattern
                match_cell = next(
                    (c for c in cells if " v " in c or " vs " in c), None
                )
                if not match_cell:
                    continue
                sep = " vs " if " vs " in match_cell else " v "
                parts = match_cell.split(sep)
                if len(parts) != 2:
                    continue
                home_team, away_team = parts[0].strip(), parts[1].strip()

                # Find prediction cell (1/X/2)
                pred_raw = next(
                    (
                        c
                        for c in cells
                        if c in ("1", "X", "2", "1X", "X2", "12")
                    ),
                    None,
                )
                side_map = {"1": "Home (1)", "X": "Draw (X)", "2": "Away (2)"}
                predicted_side = side_map.get(pred_raw) if pred_raw else None

                if home_team and away_team and predicted_side:
                    predictions.append(
                        {
                            "home_team": home_team,
                            "away_team": away_team,
                            "date": date_str,
                            "source": "PREDICTZ",
                            "predicted_side": predicted_side,
                            "confidence": 60.0,
                            "predicted_ou": None,
                            "avg_goals": None,
                        }
                    )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[PREDICTZ] scrape failed: {e}")

    logger.info(f"[PREDICTZ] {len(predictions)} predictions")
    return predictions


# ─────────────────────────────────────────────
# SOURCE 3 — ScoreAxis / soccerpunter (requests)
# ─────────────────────────────────────────────

def get_soccerpunter_predictions(date_str: str | None = None) -> list[dict]:
    """Fetch predictions from soccerpunter.com (statistics-based, free)."""
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    url = f"https://www.soccerpunter.com/soccer-statistics/2026-{date_str[5:]}-match-predictions.html"
    try:
        r = requests.get(url, headers=_REQ_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        logger.warning(f"[SOCCERPUNTER] fetch failed: {e}")
        return []

    predictions = []
    rows = soup.select("table.sched tbody tr, table.competitionRanking tbody tr")
    for row in rows:
        try:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 5:
                continue
            # Look for home vs away split
            home = row.find("td", class_=lambda c: c and "home" in c.lower())
            away = row.find("td", class_=lambda c: c and "away" in c.lower())
            if not home or not away:
                continue
            home_team = home.get_text(strip=True)
            away_team = away.get_text(strip=True)
            # Find 1/X/2 tip
            tip = next((c for c in cells if c in ("1", "X", "2")), None)
            side_map = {"1": "Home (1)", "X": "Draw (X)", "2": "Away (2)"}
            if tip and home_team and away_team:
                predictions.append({
                    "home_team": home_team,
                    "away_team": away_team,
                    "date": date_str,
                    "source": "SOCCERPUNTER",
                    "predicted_side": side_map[tip],
                    "confidence": 55.0,
                    "predicted_ou": None,
                    "avg_goals": None,
                })
        except Exception:
            pass

    logger.info(f"[SOCCERPUNTER] {len(predictions)} predictions")
    return predictions


# ─────────────────────────────────────────────
# SOURCE 4 — API-Football Predictions endpoint (percent-based model)
# ─────────────────────────────────────────────
# A second, decorrelated paper-bet signal run alongside Forebet (source=APIFB)
# for a clean A/B comparison in the research ledger -- see edge_milestone_check.py.
# Free tier = 100 requests/day and settlement (fetch_api_football_results() in
# live_predictions_daemon.py) already spends ~3/day, so this stays hard
# budget-conscious: skip entirely without a key or without Betarabia fixtures
# to match against, fetch the day's fixture list in ONE request, keep only
# fixtures Betarabia/Kambi actually price, and cache each fixture's prediction
# per calendar day so repeat calls never re-spend the per-fixture budget.

_APIFB_URL_FIXTURES = "https://v3.football.api-sports.io/fixtures"
_APIFB_URL_PREDICTIONS = "https://v3.football.api-sports.io/predictions"
_APIFB_MAX_PER_DAY = 40  # prediction-fetch budget; well under the 100/day free quota
_apifb_predictions_cache: dict[str, dict] = {}  # date_str -> {fixture_id: pred_dict_or_None}


def _api_football_key(base_dir: str | None = None) -> str | None:
    """Resolve API_FOOTBALL_KEY from the environment, falling back to reading
    .env directly -- os.getenv alone can return empty in daemon threads since
    .env isn't loaded into os.environ there (same fallback pattern as
    fetch_api_football_results() in live_predictions_daemon.py)."""
    key = os.getenv("API_FOOTBALL_KEY")
    if key:
        return key
    if base_dir is None:
        base_dir = BASE_DIR
    try:
        with open(os.path.join(base_dir, ".env"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("API_FOOTBALL_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def _fetch_apifb_fixtures(date_str: str, key: str) -> list[dict]:
    """GET /fixtures?date=... -> [{fixture_id, home_team, away_team}, ...]. One request."""
    try:
        r = requests.get(
            _APIFB_URL_FIXTURES,
            headers={"x-apisports-key": key},
            params={"date": date_str},
            timeout=20,
        )
        payload = r.json()
        if payload.get("errors"):
            logger.warning(f"[APIFB] fixtures fetch error for {date_str}: {payload['errors']}")
            return []
        data = payload.get("response", [])
    except Exception as e:
        logger.warning(f"[APIFB] fixtures fetch failed for {date_str}: {e}")
        return []

    out = []
    for fx in data:
        fixture = fx.get("fixture") or {}
        teams = fx.get("teams") or {}
        lg = fx.get("league") or {}
        fid = fixture.get("id")
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        if fid is not None and home and away:
            out.append({
                "fixture_id": fid, "home_team": home, "away_team": away,
                "league": lg.get("name"), "country": lg.get("country"),
            })
    # Persist nation/league metadata for the whole day's fixtures (costs no
    # extra quota — same response). Used by the ntfy pick alerts to tell the
    # user WHICH country/league a pick is in (2026-07-13 request).
    try:
        import json

        with open(
            os.path.join(BASE_DIR, "data", "apifb_fixture_meta.json"), "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                {"date": date_str, "fixtures": [
                    {"home": o["home_team"], "away": o["away_team"],
                     "league": o["league"], "country": o["country"]}
                    for o in out
                ]},
                f,
            )
    except Exception as e:
        logger.debug(f"[APIFB] fixture meta persist failed: {e}")
    return out


def lookup_nation_league(home: str, away: str):
    """(country, league) for a fixture, resolved by fuzzy team-name match
    against the persisted API-Football fixtures metadata — or None when the
    file is missing or no fixture matches. Read-only; never raises."""
    try:
        import json

        with open(
            os.path.join(BASE_DIR, "data", "apifb_fixture_meta.json"),
            encoding="utf-8",
        ) as f:
            fixtures = (json.load(f) or {}).get("fixtures") or []
    except Exception:
        return None
    best = None
    for fx in fixtures:
        h = get_match_score(home, fx.get("home") or "")
        a = get_match_score(away, fx.get("away") or "")
        if h >= 0.5 and a >= 0.5:
            score = h + a
            if best is None or score > best[0]:
                best = (score, fx.get("country"), fx.get("league"))
    if best is None:
        return None
    return best[1], best[2]


def _fetch_apifb_prediction(fixture_id, key: str) -> dict | None:
    """GET /predictions?fixture=... -> the raw prediction payload for one fixture,
    or None. One request per call -- callers must budget these."""
    try:
        r = requests.get(
            _APIFB_URL_PREDICTIONS,
            headers={"x-apisports-key": key},
            params={"fixture": fixture_id},
            timeout=20,
        )
        payload = r.json()
        if payload.get("errors"):
            logger.debug(
                f"[APIFB] prediction fetch error for fixture {fixture_id}: {payload['errors']}"
            )
            return None
        data = payload.get("response", [])
        return data[0] if data else None
    except Exception as e:
        logger.debug(f"[APIFB] prediction fetch failed for fixture {fixture_id}: {e}")
        return None


def _parse_apifb_prediction(
    raw: dict | None, home_team: str, away_team: str, date_str: str
) -> dict | None:
    """Parse one API-Football /predictions response entry into the shared
    tipster-prediction dict shape ({home_team, away_team, source, predicted_side,
    confidence, predicted_ou, ...}). Returns None when the percent breakdown --
    the minimum needed to pick a side and a confidence -- is missing or unusable.
    """
    if not raw:
        return None
    preds = raw.get("predictions") or {}
    percent = preds.get("percent") or {}

    def _pct(v):
        try:
            return float(str(v).strip().rstrip("%"))
        except (TypeError, ValueError):
            return None

    prob_home = _pct(percent.get("home"))
    prob_draw = _pct(percent.get("draw"))
    prob_away = _pct(percent.get("away"))
    if prob_home is None or prob_draw is None or prob_away is None:
        return None

    maxp = max(prob_home, prob_draw, prob_away)
    if maxp == prob_home:
        predicted_side = "Home (1)"
    elif maxp == prob_draw:
        predicted_side = "Draw (X)"
    else:
        predicted_side = "Away (2)"

    # under_over is API-Football's signed goals-line advice, e.g. "-2.5" (predicts
    # under) or "+2.5" (predicts over). Only the sign is used; the line is fixed
    # at 2.5 to match the rest of the pipeline's O/U convention.
    predicted_ou = None
    under_over = preds.get("under_over")
    if under_over:
        s = str(under_over).strip()
        if s.startswith("-"):
            predicted_ou = "Under 2.5"
        elif s.startswith("+"):
            predicted_ou = "Over 2.5"

    return {
        "home_team": home_team,
        "away_team": away_team,
        "date": date_str,
        "source": "APIFB",
        "predicted_side": predicted_side,
        "confidence": float(maxp),
        "predicted_ou": predicted_ou,
        "ou_confidence": None,
        "avg_goals": None,
        "prob_home": prob_home,
        "prob_draw": prob_draw,
        "prob_away": prob_away,
    }


def _filter_apifb_fixtures_matched(
    apifb_fixtures: list[dict], betarabia_fixtures: list[dict], limit: int
) -> list[dict]:
    """Keep only API-Football fixtures that a Betarabia/Kambi fixture actually
    prices (fuzzy team-name match via name_matching.get_match_score, the same
    age-group-aware matcher the settlement pipeline uses), capped at `limit` --
    the free-tier prediction-fetch budget.
    """
    if not apifb_fixtures or not betarabia_fixtures:
        return []
    matched = []
    for af in apifb_fixtures:
        for bf in betarabia_fixtures:
            if (
                get_match_score(af.get("home_team"), bf.get("home_team")) >= 0.5
                and get_match_score(af.get("away_team"), bf.get("away_team")) >= 0.5
            ):
                matched.append(af)
                break
        if len(matched) >= limit:
            break
    return matched


def get_api_football_predictions(
    date_str: str | None = None, odds_db: str | None = None
) -> list[dict]:
    """
    API-Football Predictions endpoint -- a second, decorrelated paper-bet
    signal run alongside Forebet for an A/B comparison (source='APIFB').

    Skips entirely (no network spent) without a key or without any Betarabia
    fixtures to match against. Otherwise: one request to list the day's
    fixtures, filter to fixtures Betarabia/Kambi actually price and cap at
    _APIFB_MAX_PER_DAY, then one prediction request per NEW (uncached)
    fixture -- a fixture already fetched today is served from cache.
    """
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    key = _api_football_key()
    if not key:
        return []

    if odds_db is None:
        odds_db = os.path.join(BASE_DIR, "data", "odds_stream.db")
    betarabia_fixtures = _load_betarabia_fixtures(odds_db)
    if not betarabia_fixtures:
        return []

    apifb_fixtures = _fetch_apifb_fixtures(date_str, key)
    if not apifb_fixtures:
        return []

    matched = _filter_apifb_fixtures_matched(
        apifb_fixtures, betarabia_fixtures, _APIFB_MAX_PER_DAY
    )

    cache = _apifb_predictions_cache.setdefault(date_str, {})
    predictions = []
    fetched = 0
    for af in matched:
        fid = af["fixture_id"]
        if fid in cache:
            cached_pred = cache[fid]
            if cached_pred:
                predictions.append(cached_pred)
            continue
        raw = _fetch_apifb_prediction(fid, key)
        fetched += 1
        pred = _parse_apifb_prediction(raw, af["home_team"], af["away_team"], date_str)
        cache[fid] = pred
        if pred:
            predictions.append(pred)

    logger.info(f"[APIFB] {date_str}: {len(predictions)} predictions from {fetched} API calls")
    return predictions


# ─────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────

def _mean_conf(*vals):
    vs = [float(v) for v in vals if v is not None]
    return round(sum(vs) / len(vs), 2) if vs else None


def build_consensus_predictions(predictions: list[dict]) -> list[dict]:
    """CONSENSUS mix strategy (2026-07-14): a synthetic prediction exists only
    where FOREBET and APIFB independently agree on the same side of the same
    fixture — two decorrelated models agreeing is the ensemble signal worth
    validating. Teams are fuzzy-matched (the sources name clubs differently);
    confidence is the mean of the two models'. The O/U pick rides along only
    when both models agree on it as well. Placed downstream under
    bet_source='TIPSTER_CONSENSUS' — research ledger only (the real-bankroll
    gate remains FOREBET-exclusive)."""
    fb = [p for p in predictions if p.get("source") == "FOREBET"]
    af = [p for p in predictions if p.get("source") == "APIFB"]
    out = []
    used = set()
    for f in fb:
        for i, a in enumerate(af):
            if i in used:
                continue
            if (
                get_match_score(f.get("home_team", ""), a.get("home_team", "")) >= 0.5
                and get_match_score(f.get("away_team", ""), a.get("away_team", "")) >= 0.5
            ):
                used.add(i)  # this APIFB fixture is paired either way
                side = f.get("predicted_side")
                if side and side == a.get("predicted_side"):
                    ou = (
                        f.get("predicted_ou")
                        if f.get("predicted_ou")
                        and f.get("predicted_ou") == a.get("predicted_ou")
                        else None
                    )
                    out.append(
                        {
                            "home_team": f["home_team"],
                            "away_team": f["away_team"],
                            "date": f.get("date"),
                            "source": "CONSENSUS",
                            "predicted_side": side,
                            "confidence": _mean_conf(
                                f.get("confidence"), a.get("confidence")
                            ),
                            "predicted_ou": ou,
                            "ou_confidence": _mean_conf(
                                f.get("ou_confidence"), a.get("ou_confidence")
                            )
                            if ou
                            else None,
                        }
                    )
                break
    return out


def get_all_tipster_predictions(date_str: str | None = None) -> list[dict]:
    """
    Fetch predictions from all sources and return a combined list.
    Each source's picks are kept separate (same match from 2 sources = 2 entries).
    """
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    all_preds = []

    # Forebet — most reliable
    try:
        all_preds.extend(get_forebet_predictions(date_str))
    except Exception as e:
        logger.warning(f"[TIPSTER] Forebet error: {e}")

    # API-Football — second decorrelated signal, run in parallel with Forebet
    # for a clean A/B comparison (source=APIFB, bet_source=TIPSTER_APIFB).
    try:
        all_preds.extend(get_api_football_predictions(date_str))
    except Exception as e:
        logger.warning(f"[TIPSTER] API-Football error: {e}")

    # SoccerPunter — requests-based fallback
    try:
        all_preds.extend(get_soccerpunter_predictions(date_str))
    except Exception as e:
        logger.warning(f"[TIPSTER] SoccerPunter error: {e}")

    # PredictZ — Playwright, only if others are thin
    if len(all_preds) < 10:
        try:
            all_preds.extend(get_predictz_predictions(date_str))
        except Exception as e:
            logger.warning(f"[TIPSTER] PredictZ error: {e}")

    # CONSENSUS mix — synthetic picks where FOREBET and APIFB agree.
    try:
        cons = build_consensus_predictions(all_preds)
        if cons:
            logger.info(f"[TIPSTER] CONSENSUS agreements: {len(cons)}")
        all_preds.extend(cons)
    except Exception as e:
        logger.warning(f"[TIPSTER] consensus build error: {e}")

    logger.info(f"[TIPSTER] Total predictions: {len(all_preds)}")
    return all_preds


# ─────────────────────────────────────────────
# Forebet confirmation gate — shared by the Arena (real money) and the
# paper-bet daemon. Same validated technique (+41.7% ROI, CI entirely above
# zero, n=259 in the research ledger): a pick only counts as confirmed when
# an independent Forebet.com prediction agrees with the same 1X2 side.
# ─────────────────────────────────────────────
_tipster_picks_cache = {"ts": 0.0, "picks": []}
_TIPSTER_PICKS_TTL = 1800  # 30 min — Forebet updates slowly

_TIPSTER_SIDE_TO_OUTCOME = {
    "Home (1)": "home",
    "Draw (X)": "draw",
    "Away (2)": "away",
}


def get_tipster_picks() -> list[dict]:
    """Today + tomorrow's Forebet picks, cached for _TIPSTER_PICKS_TTL seconds.

    Caches the timestamp even on a failed/empty fetch (Forebet down, timeout,
    parse error). This is called from a per-selection loop across every 1X2
    match in a cycle (~hundreds of calls); without an unconditional cache
    stamp, a single Forebet outage turns into hundreds of sequential 15-30s
    network retries and hangs the whole daemon cycle for hours. A ~30 min
    backoff on failure is also the correct fail-safe for a confirmation-
    required gate: no Forebet data in means no picks get confirmed, same as
    intended when the source genuinely disagrees.
    """
    now = time.time()
    if now - _tipster_picks_cache["ts"] < _TIPSTER_PICKS_TTL:
        return _tipster_picks_cache["picks"]
    picks = []
    try:
        today = datetime.date.today()
        picks = list(get_forebet_predictions(today.isoformat()) or [])
        try:
            picks += get_forebet_predictions(
                (today + datetime.timedelta(days=1)).isoformat()
            ) or []
        except Exception:
            pass  # tomorrow page is best-effort
    except Exception as e:
        logger.warning(f"[TIPSTER] confirm-gate fetch failed (non-fatal): {e}")
    _tipster_picks_cache["picks"] = picks
    _tipster_picks_cache["ts"] = now
    return picks


def tipster_agrees(picks: list[dict], match_name: str, outcome: str) -> bool:
    """True when Forebet's 1X2 pick for this match equals the candidate outcome."""
    if not picks or not match_name or not outcome:
        return False
    try:
        home, away = [t.strip().lower() for t in match_name.split(" vs ")[:2]]
    except ValueError:
        return False
    for p in picks:
        ph = (p.get("home_team") or "").strip().lower()
        pa = (p.get("away_team") or "").strip().lower()
        if not ph or not pa:
            continue
        if (ph in home or home in ph) and (pa in away or away in pa):
            return _TIPSTER_SIDE_TO_OUTCOME.get(p.get("predicted_side") or "") == outcome
    return False


# ─────────────────────────────────────────────
# Match tipster pick → Betarabia fixture
# ─────────────────────────────────────────────

def _load_betarabia_fixtures(odds_db: str) -> list[dict]:
    """Load upcoming fixtures from odds_stream.db."""
    try:
        conn = sqlite3.connect(odds_db)
        rows = conn.execute(
            "SELECT fixture_id, home_team, away_team, tournament_name, kickoff_time, kickoff_date "
            "FROM fixture ORDER BY kickoff_date, kickoff_time"
        ).fetchall()
        conn.close()
        return [
            {
                "fixture_id": r[0],
                "home_team": r[1],
                "away_team": r[2],
                "tournament_name": r[3],
                "kickoff_time": r[4],
                "kickoff_date": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"[TIPSTER] Could not load fixtures: {e}")
        return []


def match_to_betarabia(prediction: dict, betarabia_fixtures: list[dict]) -> dict | None:
    """
    Fuzzy-match a tipster prediction to a Betarabia fixture.
    Returns the fixture dict or None if no good match.
    """
    home = prediction["home_team"].lower().strip()
    away = prediction["away_team"].lower().strip()

    best_score = 0.0
    best_fixture = None

    for fix in betarabia_fixtures:
        fh = fix["home_team"].lower().strip()
        fa = fix["away_team"].lower().strip()

        score_h = fuzz.token_set_ratio(home, fh) / 100.0
        score_a = fuzz.token_set_ratio(away, fa) / 100.0
        combined = (score_h + score_a) / 2.0

        if combined > best_score:
            best_score = combined
            best_fixture = fix

    if best_score >= 0.70:
        return best_fixture
    return None


# ─────────────────────────────────────────────
# Place paper bets
# ─────────────────────────────────────────────

def _paper_balance() -> float:
    try:
        conn = sqlite3.connect(os.path.join(BASE_DIR, "data", "bankroll.db"))
        row = conn.execute(
            "SELECT current_balance FROM bankroll ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return float(row[0]) if row else 1000.0
    except Exception:
        return 1000.0


def _stake_params():
    """(notional, stake_min, stake_max) for conviction sizing, from
    settings.json (stake_notional / stake_min / stake_max). Defaults to the
    legacy $500 / [$2, $25] when unconfigured. Settings-driven (2026-07-13)
    because the user mirrors picks with a real bankroll — sizing must match
    the capital actually at risk, not a hardcoded research notional."""
    notional, s_min, s_max = 500.0, 2.0, 25.0
    try:
        import json

        with open(os.path.join(BASE_DIR, "data", "settings.json"), encoding="utf-8") as f:
            s = json.load(f)
        notional = float(s.get("stake_notional", notional))
        s_min = float(s.get("stake_min", s_min))
        s_max = float(s.get("stake_max", s_max))
    except Exception:
        pass
    return notional, s_min, s_max


def _conviction_stake(confidence, odds_val, balance, flat=5.0):
    """Quarter-Kelly stake from the tipster's own published confidence.

    confidence: tipster probability for the pick in percent (e.g. 63.0).
    Sized against the strategy's virtual bankroll balance (not the global
    paper bankroll) so stakes stay comparable across the ledger.
    Every path is clamped to [stake_min, stake_max] from settings."""
    notional, s_min, s_max = _stake_params()

    def _clamp(v):
        return round(max(s_min, min(s_max, float(v))), 2)

    try:
        p = float(confidence) / 100.0
        b = float(odds_val) - 1.0
        if not (0.0 < p < 1.0) or b <= 0:
            return _clamp(balance * 0.05)
        kelly_f = (p * float(odds_val) - 1.0) / b
        if kelly_f <= 0:
            return _clamp(s_min)  # tipster picked it but the price gives no Kelly edge
        return _clamp(balance * kelly_f * 0.25)
    except (TypeError, ValueError):
        return _clamp(balance * 0.05)


def _build_odds_map(market_rows) -> dict[tuple, float]:
    """
    Build the (fixture_id, market_name, selection_name) -> odds lookup used
    to price tipster bets.

    Bug fixed 2026-07-09: odds_stream.db's `market` table stores ODDS FROM
    MULTIPLE BOOKMAKERS under the exact same (fixture_id, market_name,
    selection_name) key -- e.g. a single match's "France" selection under
    "Match Result" had ~19 rows ranging from 1.00 to 12.00, one per
    bookmaker. The previous implementation built this dict with a plain
    per-row assignment, so the LAST row SQLite happened to return silently
    overwrote every earlier one -- the odds actually used to size/gate a bet
    were effectively whichever bookmaker's row was scraped/inserted last,
    not a deliberately chosen price. That surfaced as a real, live bet
    (France vs Morocco) being priced at an outlier 10.0 instead of the
    representative 1.63 most bookmakers agreed on, and got defensively
    skipped by the odds-sanity check as a result.

    Fix: collect every bookmaker's price per key and take the MEDIAN --
    robust to single-bookmaker outliers without needing to identify or
    trust one specific book.
    """
    odds_lists: dict[tuple, list] = {}
    for fid, mname, sel, odd in market_rows:
        if odd:
            odds_lists.setdefault((str(fid), mname, sel), []).append(float(odd))
    return {key: statistics.median(vals) for key, vals in odds_lists.items()}


def _parse_kickoff_dt(raw):
    """Parse a fixture kickoff (ISO datetime or date) into an aware UTC datetime,
    or None if missing/unparseable. Naive timestamps are assumed UTC."""
    if not raw:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _fixture_has_started(fix, now=None):
    """True when the fixture's recorded kickoff is at/before `now` — i.e. the
    match has already kicked off, so a "pre-match" bet on it would really be an
    in-play bet priced off stale odds (the 2026-07-11 Australian-NPL bets placed
    7-27 min AFTER kickoff).

    Fail-open (return False) when no kickoff can be parsed: never block a
    placement on ABSENT data, only on data that positively shows the match began.

    Kickertech records 00:00:00 as a DATE-ONLY placeholder when the real kickoff
    time is unknown. A same-day placeholder is treated as "time unknown" (not
    started) so a match that may still be hours away is not wrongly skipped;
    only a placeholder whose DATE is already past counts as started.
    """
    ko = _parse_kickoff_dt((fix or {}).get("kickoff_time")) or _parse_kickoff_dt(
        (fix or {}).get("kickoff_date")
    )
    if ko is None:
        return False
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)

    is_midnight_placeholder = ko.hour == 0 and ko.minute == 0 and ko.second == 0
    if is_midnight_placeholder:
        # Only the date is trustworthy: started iff that date is already past.
        return ko.date() < now.date()
    return ko <= now


def _placement_now():
    """Current UTC time for the placement-time kickoff re-check. Indirected
    through a function so tests can freeze it."""
    return datetime.datetime.now(datetime.timezone.utc)


def _allowed_tipster_sources() -> set:
    """Upper-cased set of tipster sources allowed to PLACE bets, from
    settings.json's `tipster_sources_allowed` (e.g. ["FOREBET"]).

    Empty set (key missing/empty/unreadable) = no restriction, all sources
    place — backward compatible. Enforced at the placement boundary rather
    than in the aggregator so a future source can't bypass it and the picks
    themselves remain visible for research."""
    try:
        import json

        with open(os.path.join(BASE_DIR, "data", "settings.json"), encoding="utf-8") as f:
            allowed = json.load(f).get("tipster_sources_allowed") or []
        return {str(s).upper() for s in allowed}
    except Exception:
        return set()


def place_tipster_bets(
    predictions: list[dict],
    bet_db: str | None = None,
    odds_db: str | None = None,
    stake: float = 5.0,
) -> int:
    """
    For each tipster prediction, match to a Betarabia fixture, get current odds,
    and insert a paper bet into bet_log. Returns number of bets placed.
    """
    if bet_db is None:
        bet_db = os.path.join(BASE_DIR, "data", "bet_log.db")
    if odds_db is None:
        odds_db = os.path.join(BASE_DIR, "data", "odds_stream.db")

    fixtures = _load_betarabia_fixtures(odds_db)
    if not fixtures:
        logger.warning("[TIPSTER] No Betarabia fixtures available")
        return 0

    # Load current odds from odds_stream.db
    # Schema: fixture_id, market_name, selection_name, raw_odds
    try:
        odds_conn = sqlite3.connect(odds_db)
        market_rows = odds_conn.execute(
            "SELECT fixture_id, market_name, selection_name, raw_odds FROM market"
        ).fetchall()
        odds_conn.close()
    except Exception as e:
        logger.warning(f"[TIPSTER] Could not load odds: {e}")
        return 0

    odds_map = _build_odds_map(market_rows)

    # Also build a selection normaliser for Match Result → 1X2 side
    # Betarabia uses home_team name, "X", and away_team name as selections
    fixture_by_id = {f["fixture_id"]: f for f in fixtures}

    # Load bet_log schema
    try:
        bet_conn = sqlite3.connect(bet_db)
        cols = [r[1] for r in bet_conn.execute("PRAGMA table_info(bet_log)").fetchall()]
    except Exception as e:
        logger.warning(f"[TIPSTER] Could not open bet_log: {e}")
        return 0

    placed = 0
    now_utc = datetime.datetime.utcnow().isoformat()
    _now_dt = _placement_now()  # aware UTC; for the in-play kickoff re-check
    _src_allowed = _allowed_tipster_sources()  # Forebet-only mode etc.
    _balance = _paper_balance()

    already_open = set()
    try:
        open_rows = bet_conn.execute(
            "SELECT fixture_id FROM bet_log WHERE result='OPEN'"
        ).fetchall()
        already_open = {str(r[0]) for r in open_rows if r[0]}
    except Exception:
        pass

    # Kambi (Unibet) fallback for fixtures Betarabia doesn't cover -- e.g.
    # Australian NPL state leagues, Korean lower tiers, that Forebet publishes
    # picks for but Betarabia's ~47-fixture feed never has. Lazy-loaded (at
    # most one HTTP call per place_tipster_bets() invocation, only if a
    # Betarabia miss actually happens) and 1X2-only (Kambi has no O/U data).
    _kambi_cache = None

    for pred in predictions:
        try:
            # Source whitelist (settings.tipster_sources_allowed): in
            # Forebet-only mode every other source's picks are research-visible
            # but never placed. Checked first so blocked sources cost nothing.
            if _src_allowed and str(pred.get("source", "")).upper() not in _src_allowed:
                continue

            fix = match_to_betarabia(pred, fixtures)
            book_used = "Betarabia"
            km = None
            if fix is None:
                if _kambi_cache is None:
                    try:
                        from src.kambi_scraper import fetch_kambi_1x2

                        _kambi_cache = fetch_kambi_1x2() or {}
                    except Exception as e:
                        logger.debug(f"[TIPSTER] Kambi fallback unavailable: {e}")
                        _kambi_cache = {}
                if _kambi_cache:
                    from src.line_shop import match_kambi_fixture

                    km = match_kambi_fixture(
                        pred["home_team"], pred["away_team"], _kambi_cache
                    )
                if km:
                    fix = {
                        "fixture_id": _make_kambi_fixture_id(
                            km["home_team"], km["away_team"]
                        ),
                        "home_team": km["home_team"],
                        "away_team": km["away_team"],
                        "tournament_name": km.get("league"),
                    }
                    book_used = "Kambi"
                else:
                    logger.debug(
                        f"[TIPSTER] No Betarabia/Kambi match for {pred['home_team']} vs {pred['away_team']}"
                    )
                    continue

            fid = str(fix["fixture_id"])
            source = pred["source"]

            # In-play placement guard (kickoff re-check): never place a "pre-match"
            # bet on a fixture whose kickoff has already passed — that is an in-play
            # bet on stale pre-match odds (the 2026-07-11 Australian-NPL bets placed
            # 7-27 min AFTER kickoff). Fixtures with no/placeholder kickoff fail open.
            if _fixture_has_started(fix, _now_dt):
                logger.debug(
                    f"[TIPSTER] Skipped {fix['home_team']} vs {fix['away_team']} "
                    f"— already kicked off (in-play); pre-match odds are stale."
                )
                continue

            # Determine what to bet: 1X2 and/or O/U
            bets_to_place = []

            # 1X2 bet based on predicted_side
            side_1x2 = pred.get("predicted_side")
            if side_1x2:
                if book_used == "Kambi":
                    # Kambi's feed already resolves straight to home/draw/away
                    # odds -- no Betarabia-style selection-string lookup needed.
                    sel_label = side_1x2
                    odds_val = _kambi_odds_for_side(km, side_1x2)
                else:
                    sel_label = _resolve_selection(side_1x2, fix, odds_map, fid)
                    odds_val = (
                        odds_map.get((fid, "Match Result", sel_label))
                        if sel_label
                        else None
                    )
                if sel_label:
                    # Sanity: if Forebet's confidence implies prob > 40%, odds can't
                    # legitimately be > 8.0 — that would mean a >5x mispricing, which
                    # indicates the wrong selection was resolved. Skip to avoid bad data.
                    conf = pred.get("confidence") or 0
                    max_sane_odds = max(8.0, round(100.0 / conf, 1)) if conf > 0 else 8.0
                    if odds_val and 1.05 < odds_val <= max_sane_odds:
                        bets_to_place.append(
                            ("1X2", side_1x2, "Match Result", sel_label, odds_val)
                        )
                    elif odds_val and odds_val > max_sane_odds:
                        logger.debug(
                            f"[TIPSTER] Skipped 1X2 {side_1x2} @ {odds_val:.2f} — "
                            f"odds too high for {conf}% confidence (max_sane={max_sane_odds:.1f}), "
                            f"likely wrong selection resolved for {fix['home_team']} vs {fix['away_team']}"
                        )

            # O/U bet if predicted (Betarabia uses "Total Goals" market; Kambi
            # has no O/U data, see fetch_kambi_1x2()'s docstring, so skip it
            # entirely for Kambi-sourced fixtures)
            ou_side = pred.get("predicted_ou") if book_used == "Betarabia" else None
            if ou_side:
                # Try common Betarabia O/U selection naming patterns
                over_names = ["Total OVER 2.5", "Total OVER  2.5", "Over 2.5", "OVER 2.5", "OVER"]
                under_names = ["Total UNDER 2.5", "Total UNDER  2.5", "Under 2.5", "UNDER 2.5", "UNDER"]
                candidates = over_names if ou_side == "Over 2.5" else under_names
                ou_odds = None
                ou_sel_used = None
                for mname in ["Total Goals", "Goals Over/Under", "Total Goals Over/Under"]:
                    for cand in candidates:
                        v = odds_map.get((fid, mname, cand))
                        if v:
                            ou_odds = v
                            ou_sel_used = cand
                            break
                    if ou_odds:
                        break
                if ou_odds and ou_odds > 1.05:
                    bets_to_place.append(
                        ("Over/Under 2.5", ou_side, "Total Goals", ou_sel_used, ou_odds)
                    )

            for market_type, side, raw_mtype, raw_sel, odds_val in bets_to_place:
                bet_id = _make_bet_id(source, fid, market_type, side)

                # bet_id is deterministic (fixture+market+side), so re-scraping
                # today's same Forebet picks on a later cycle regenerates the
                # same id. The INSERT below is OR IGNORE and silently no-ops on
                # that duplicate — but the real-bankroll gate must never charge
                # a stake for a bet that won't actually be (re-)inserted, so
                # check existence BEFORE touching real_bankroll.db.
                if bet_conn.execute(
                    "SELECT 1 FROM bet_log WHERE bet_id=?", (bet_id,)
                ).fetchone():
                    continue

                # Conviction sizing: quarter-Kelly from the tipster's own
                # published confidence (1X2). O/U picks carry no confidence
                # number, so they get a mild default conviction.
                _conf = (
                    pred.get("confidence")
                    if market_type == "1X2"
                    else pred.get("ou_confidence") or 55.0
                )
                # Get the strategy's own virtual bankroll balance (fair evaluation at $100.00 starting balance)
                strategy_balance = 100.0
                try:
                    from src.strategy_ledger import strategy_ledgers
                    ledgers = strategy_ledgers(bet_db)
                    strat_id = f"TIPSTER_{source}"
                    led = ledgers.get(strat_id)
                    if led:
                        strategy_balance = float(led["balance"])
                except Exception as _br_err:
                    logger.warning(f"[BANKROLL] strategy_ledgers fetch failed: {_br_err}")
                strategy_balance = max(10.0, strategy_balance)

                _stake = _conviction_stake(_conf, odds_val, strategy_balance, flat=stake)

                # The winning strategy: only Forebet-confirmed picks risk the
                # real $200 bankroll. Gate + deduct here so real_bankroll.db's
                # halt/drawdown/exposure/balance limits are enforced exactly
                # like every other live staking path. Other tipster sources
                # are ungated research and never touch this bankroll.
                if source == "FOREBET":
                    try:
                        from src.bankroll_tracker import register_bet as _real_register_bet

                        if not _real_register_bet(_stake, db_path=REAL_BANKROLL_DB):
                            logger.debug(
                                f"[TIPSTER_FOREBET] Skipped {fix['home_team']} vs "
                                f"{fix['away_team']} — real bankroll declined the bet."
                            )
                            continue
                    except Exception as e:
                        logger.warning(f"[TIPSTER_FOREBET] real bankroll gate failed: {e}")
                        continue

                row_vals = _build_row(
                    cols=cols,
                    bet_id=bet_id,
                    fix=fix,
                    market_type=market_type,
                    side=side,
                    odds_val=odds_val,
                    stake=_stake,
                    bet_source=f"TIPSTER_{source}",
                    placed_at=now_utc,
                    book=book_used,
                )
                try:
                    bet_conn.execute(
                        f"INSERT OR IGNORE INTO bet_log ({','.join(cols)}) "
                        f"VALUES ({','.join(['?']*len(cols))})",
                        row_vals,
                    )
                    if bet_conn.total_changes > 0:
                        placed += 1
                        logger.debug(
                            f"[TIPSTER_{source}] {fix['home_team']} vs {fix['away_team']} "
                            f"| {market_type} {side} @ {odds_val:.2f}"
                        )
                except Exception as e:
                    logger.debug(f"[TIPSTER] insert error: {e}")

        except Exception as e:
            logger.debug(f"[TIPSTER] prediction error: {e}")

    bet_conn.commit()
    bet_conn.close()
    logger.info(f"[TIPSTER] Placed {placed} paper bets from {len(predictions)} predictions")
    return placed


def _resolve_selection(
    side: str, fix: dict, odds_map: dict, fid: str
) -> str | None:
    """Map Home(1)/Draw(X)/Away(2) to the Betarabia selection string in the market table.

    Strict mode only — no fuzzy fallback. Fuzzy matching was returning the wrong
    team's selection for mismatched names, causing opponent odds to be logged instead
    of the actual bet price. Skip the bet if we can't find a clean exact match.
    """
    if side == "Home (1)":
        candidates = [fix["home_team"], "Home", "1"]
    elif side == "Draw (X)":
        candidates = ["X", "Draw", "draw"]
    elif side == "Away (2)":
        candidates = [fix["away_team"], "Away", "2"]
    else:
        return None

    for c in candidates:
        if (fid, "Match Result", c) in odds_map:
            return c

    # No exact match found — skip rather than risk returning wrong odds.
    return None


def _kambi_odds_for_side(km: dict, side: str):
    """
    Map Home(1)/Draw(X)/Away(2) directly to Kambi's already-resolved
    home/draw/away odds (fetch_kambi_1x2()'s dict shape) -- no
    selection-string matching needed, unlike Betarabia's odds_map.
    """
    key = {"Home (1)": "home", "Draw (X)": "draw", "Away (2)": "away"}.get(side)
    if key is None:
        return None
    val = km.get(key)
    return float(val) if val else None


def _make_kambi_fixture_id(home_team: str, away_team: str) -> str:
    """Stable synthetic fixture_id for a Kambi-sourced (non-Betarabia) match."""
    raw = f"{home_team}|{away_team}".lower()
    return "KAMBI_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _make_bet_id(source: str, fid: str, market: str, side: str) -> str:
    raw = f"TIPSTER_{source}_{fid}_{market[:3]}_{side[:3]}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"TIP_{source[:4]}_{fid}_{h}"


def _build_row(cols, bet_id, fix, market_type, side, odds_val, stake, bet_source, placed_at, book="Betarabia"):
    """Build a tuple matching the bet_log column order."""
    field_map = {
        "bet_id": bet_id,
        "match_id": f"{fix['home_team']} vs {fix['away_team']}",
        "player_id": f"{fix['home_team']} vs {fix['away_team']} ({side})",
        "market_type": market_type,
        "line": 2.5,
        "side": side,
        "entry_odds": odds_val,
        "fair_odds": odds_val,
        "edge_pct": 0.0,
        "stake": stake,
        "book": book,
        "placed_at": placed_at,
        "lineup_drop_at": None,
        "latency_ms": None,
        "closing_odds": None,
        "clv": None,
        "result": "OPEN",
        "pnl": 0,
        "regime": None,
        "role_shift_flag": None,
        "bet_source": bet_source,
        "is_recommended": 1,
        "model_version": None,
        "fixture_id": fix["fixture_id"],
        "league": fix.get("tournament_name"),
        "kickoff_time": fix.get("kickoff_time") or fix.get("kickoff_date"),
        "clv_sharp": None,
        "best_odds": odds_val,
        "best_book": book,
        "signal_name": bet_source,
        "move_size": None,
        "monotonicity": None,
        "pinnacle_clv": None,
    }
    return tuple(field_map.get(c) for c in cols)


# ─────────────────────────────────────────────
# Daemon integration helper
# ─────────────────────────────────────────────

_last_run_date: str | None = None


def run_tipster_cycle() -> int:
    """
    Called by the daemon once per day (or on demand).
    Fetches predictions and places paper bets. Returns bet count.
    """
    global _last_run_date
    today = datetime.date.today().isoformat()
    if _last_run_date == today:
        return 0  # already ran today
    _last_run_date = today

    preds = get_all_tipster_predictions(today)
    if not preds:
        logger.info("[TIPSTER] No predictions fetched today")
        return 0

    n = place_tipster_bets(preds)
    logger.info(f"[TIPSTER] Daily cycle complete: {n} bets placed from {len(preds)} predictions")
    return n


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    preds = get_all_tipster_predictions(date_arg)
    print(f"\nTotal predictions: {len(preds)}")
    by_source: dict[str, int] = {}
    for p in preds:
        by_source[p["source"]] = by_source.get(p["source"], 0) + 1
    for src, cnt in by_source.items():
        print(f"  {src}: {cnt}")
    print("\nSample picks:")
    for p in preds[:8]:
        print(
            f"  [{p['source']}] {p['home_team']} vs {p['away_team']} → "
            f"{p['predicted_side']} (conf {p['confidence']:.0f}%) "
            f"| O/U: {p.get('predicted_ou') or '-'} (avg {p.get('avg_goals') or '-'} goals)"
        )
    placed = place_tipster_bets(preds)
    print(f"\nPaper bets placed: {placed}")
