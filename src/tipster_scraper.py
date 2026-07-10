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

def get_forebet_predictions(date_str: str | None = None) -> list[dict]:
    """
    Fetch today's (or a specific day's) predictions from Forebet.
    Returns list of prediction dicts.
    """
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    today = datetime.date.today()
    target = datetime.date.fromisoformat(date_str)
    delta = (target - today).days

    if delta == 0:
        url = "https://www.forebet.com/en/football-tips-and-predictions-for-today"
    elif delta == 1:
        url = "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow"
    else:
        url = f"https://www.forebet.com/en/football-tips-and-predictions-for-today"

    try:
        r = requests.get(url, headers=_REQ_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"[FOREBET] fetch failed: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    predictions = []

    # Each prediction row is div.rcnt (alternates tr_0 / tr_1)
    rows = soup.find_all("div", class_="rcnt")
    logger.info(f"[FOREBET] {len(rows)} prediction rows found")

    for row in rows:
        try:
            pred = _parse_forebet_row(row, date_str)
            if pred:
                predictions.append(pred)
        except Exception as e:
            logger.debug(f"[FOREBET] row parse error: {e}")

    logger.info(f"[FOREBET] Parsed {len(predictions)} predictions")
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
# Aggregator
# ─────────────────────────────────────────────

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


def _conviction_stake(confidence, odds_val, balance, flat=5.0):
    """Quarter-Kelly stake from the tipster's own published confidence.

    confidence: tipster probability for the pick in percent (e.g. 63.0).
    Sized against a FIXED $500 notional (not the drifting paper bankroll) so
    stakes stay comparable across the whole research ledger and actually
    graduate with conviction instead of pinning to the clamps. Falls back to
    the flat stake when confidence/odds are missing. Clamped to [$2, $25].
    """
    NOTIONAL = 500.0
    try:
        p = float(confidence) / 100.0
        b = float(odds_val) - 1.0
        if not (0.0 < p < 1.0) or b <= 0:
            return flat
        kelly_f = (p * float(odds_val) - 1.0) / b
        if kelly_f <= 0:
            return 2.0  # tipster picked it but the price gives no Kelly edge
        stake = NOTIONAL * kelly_f * 0.25
        return round(max(2.0, min(25.0, stake)), 2)
    except (TypeError, ValueError):
        return flat


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
                _stake = _conviction_stake(_conf, odds_val, _balance, flat=stake)

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
