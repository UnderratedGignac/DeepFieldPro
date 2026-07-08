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
import time

import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

    # Build odds lookup: (fixture_id, market_name, selection_name) → odds
    odds_map: dict[tuple, float] = {}
    for fid, mname, sel, odd in market_rows:
        if odd:
            odds_map[(str(fid), mname, sel)] = float(odd)

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

    for pred in predictions:
        try:
            fix = match_to_betarabia(pred, fixtures)
            if fix is None:
                logger.debug(
                    f"[TIPSTER] No Betarabia match for {pred['home_team']} vs {pred['away_team']}"
                )
                continue

            fid = str(fix["fixture_id"])
            source = pred["source"]

            # Determine what to bet: 1X2 and/or O/U
            bets_to_place = []

            # 1X2 bet based on predicted_side
            side_1x2 = pred.get("predicted_side")
            if side_1x2:
                betarabia_sel = _resolve_selection(side_1x2, fix, odds_map, fid)
                if betarabia_sel:
                    odds_val = odds_map.get((fid, "Match Result", betarabia_sel))
                    if odds_val and odds_val > 1.05:
                        bets_to_place.append(
                            ("1X2", side_1x2, "Match Result", betarabia_sel, odds_val)
                        )

            # O/U bet if predicted (Betarabia uses "Total Goals" market)
            ou_side = pred.get("predicted_ou")
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

                # Conviction sizing: quarter-Kelly from the tipster's own
                # published confidence (1X2). O/U picks carry no confidence
                # number, so they get a mild default conviction.
                _conf = (
                    pred.get("confidence")
                    if market_type == "1X2"
                    else pred.get("ou_confidence") or 55.0
                )
                _stake = _conviction_stake(_conf, odds_val, _balance, flat=stake)

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
    """Map Home(1)/Draw(X)/Away(2) to the Betarabia selection string in the market table."""
    if side == "Home (1)":
        candidates = [fix["home_team"], "Home", "1"]
    elif side == "Draw (X)":
        candidates = ["X", "Draw"]
    elif side == "Away (2)":
        candidates = [fix["away_team"], "Away", "2"]
    else:
        return None

    for c in candidates:
        if (fid, "Match Result", c) in odds_map:
            return c

    # Fuzzy fallback: find any Match Result selection for this fixture
    mkt_sels = [sel for (f, m, sel) in odds_map if f == fid and m == "Match Result"]
    if not mkt_sels:
        return None

    if side == "Draw (X)":
        return next((s for s in mkt_sels if s.upper() in ("X", "DRAW")), None)
    if side == "Home (1)":
        home_name = fix["home_team"].lower()
        best = max(mkt_sels, key=lambda s: fuzz.token_set_ratio(s.lower(), home_name))
        return best if fuzz.token_set_ratio(best.lower(), home_name) > 60 else None
    if side == "Away (2)":
        away_name = fix["away_team"].lower()
        best = max(mkt_sels, key=lambda s: fuzz.token_set_ratio(s.lower(), away_name))
        return best if fuzz.token_set_ratio(best.lower(), away_name) > 60 else None

    return None


def _make_bet_id(source: str, fid: str, market: str, side: str) -> str:
    raw = f"TIPSTER_{source}_{fid}_{market[:3]}_{side[:3]}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"TIP_{source[:4]}_{fid}_{h}"


def _build_row(cols, bet_id, fix, market_type, side, odds_val, stake, bet_source, placed_at):
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
        "book": "Betarabia",
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
        "best_book": "Betarabia",
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
