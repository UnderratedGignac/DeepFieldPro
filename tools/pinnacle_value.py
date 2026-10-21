"""
pinnacle_value.py — Live Pinnacle vs soft-book value detector.

Strategy (documented ROI 3-7%):
  Compare current Betarabia odds to de-vigged Pinnacle fair price.
  When Betarabia is >= pinnacle_fair * (1 + min_edge), place a PINNACLE_VALUE bet.

This is the most evidence-backed profitable strategy in sports betting:
  - Individual books are NOT efficient relative to Pinnacle (Forrest & Simmons 2000)
  - Soft book value vs Pinnacle: 3-7% ROI (professional bettor documented results)
  - CLV from this approach is provably positive when it fires
"""

import math
import os
import sqlite3
from difflib import SequenceMatcher

from src.name_matching import _level_signature


_SIDE_MIN_SIMILARITY = 0.5
# A Pinnacle price must belong to the fixture's own kickoff: same-name games in
# other competitions (youth, reserves, women) kick off hours apart.
_KICKOFF_WINDOW_SEC = 3 * 3600


def _side_ok(name: str, cand: str) -> bool:
    """Each team must match on its own; a long shared home name is not enough.

    Scoring only the joined "home vs away" string resolved "Independiente
    Santa Fe vs Once Caldas" to Santa Fe vs Corinthians.
    """
    a, b = _normalize_team(name), _normalize_team(cand)
    if not a or not b:
        return False
    return a == b or a in b or b in a or SequenceMatcher(None, a, b).ratio() >= _SIDE_MIN_SIMILARITY


def _to_ts(kickoff):
    """Epoch seconds from a float or an ISO string; None when unparseable."""
    if kickoff is None:
        return None
    try:
        return float(kickoff)
    except (TypeError, ValueError):
        pass
    try:
        import datetime as _dt

        d = _dt.datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=_dt.timezone.utc)
        return d.timestamp()
    except Exception:
        return None


def _same_level(home: str, away: str, cand_home: str, cand_away: str) -> bool:
    """True when both sides are the same squad level (senior / uNN / reserve / youth).

    Name similarity alone matched "Lille (U-19)" to the senior "Lille" (Youth
    League fixtures mirror the Champions League on the same day).
    """
    return _level_signature(home) == _level_signature(cand_home) and _level_signature(
        away
    ) == _level_signature(cand_away)

_COMPLETED_DB = os.path.join(
    os.path.dirname(__file__), "..", "data", "deepfield_browser_data", "completed_fixtures.db"
)

# Map daemon selection labels → Pinnacle selection strings
_SEL_MAP = {
    "Home (1)": "home",
    "Draw (X)": "draw",
    "Away (2)": "away",
    "home": "home",
    "draw": "draw",
    "away": "away",
    "1": "home",
    "X": "draw",
    "2": "away",
}

# Common club name aliases that differ between Pinnacle and Betarabia/Sofascore
_TEAM_ALIASES = {
    "manchester city": "man city",
    "manchester united": "man utd",
    "nottingham forest": "nottm forest",
    "wolverhampton": "wolves",
    "tottenham hotspur": "tottenham",
    "atletico madrid": "atletico",
    "atlético madrid": "atletico",
    "paris saint-germain": "psg",
    "paris saint germain": "psg",
    "borussia dortmund": "dortmund",
    "bayer leverkusen": "leverkusen",
    "rb leipzig": "leipzig",
    "red bull leipzig": "leipzig",
    "internazionale": "inter",
    "inter milan": "inter",
    "ac milan": "milan",
    "as roma": "roma",
    "ss lazio": "lazio",
    "real madrid": "real madrid",
    "deportivo alaves": "alaves",
    "deportivo alavés": "alaves",
    "rcd espanyol": "espanyol",
    "cd leganes": "leganes",
    "united states": "usa",
    "new zealand": "new zealand",
}


def _normalize_team(name: str) -> str:
    """Normalize a team name for fuzzy matching.

    Strips punctuation, lowercases, removes common suffixes (FC, CF, SC, AFC, etc.),
    then applies known aliases so 'Manchester City' and 'Man City' collapse to the same key.
    """
    if not name:
        return ""
    n = name.lower().strip()
    # Remove punctuation except spaces
    for ch in ".,'-":
        n = n.replace(ch, " ")
    # Collapse multiple spaces
    n = " ".join(n.split())
    # Strip common club suffixes that differ between sources
    for suffix in (" fc", " cf", " sc", " afc", " fk", " sk", " bk", " if",
                   " united", " city", " town", " athletic", " wanderers",
                   " rovers", " hotspur", " albion"):
        if n.endswith(suffix):
            n = n[: -len(suffix)].rstrip()
            break
    # Apply alias table
    n = _TEAM_ALIASES.get(n, n)
    return n


def _fuzzy_match_ou25(home: str, away: str, candidates: dict, threshold: float = 0.72):
    """Find the best OU25 Pinnacle entry matching the given home/away names.

    candidates: dict keyed by "PinHome vs PinAway" → ou25_data
    Returns the matching ou25_data dict or None when no match is confident enough.
    Uses SequenceMatcher similarity on the normalised team pair string.
    """
    h_n = _normalize_team(home)
    a_n = _normalize_team(away)
    query = f"{h_n} vs {a_n}"

    best_score = 0.0
    best_val = None
    for key, val in candidates.items():
        parts = key.split(" vs ", 1)
        if len(parts) != 2 or not _same_level(home, away, parts[0], parts[1]):
            continue
        if not (_side_ok(home, parts[0]) and _side_ok(away, parts[1])):
            continue
        candidate = f"{_normalize_team(parts[0])} vs {_normalize_team(parts[1])}"
        score = SequenceMatcher(None, query, candidate).ratio()
        if score > best_score:
            best_score = score
            best_val = val

    return best_val if best_score >= threshold else None


def entry_for_fixture(home: str, away: str, kickoff, candidates: dict):
    """The Pinnacle entry (O/U 2.5, BTTS — any 'Home vs Away' keyed dict with
    starts_ts) for THIS fixture: exact name, then fuzzy, and only if it kicks
    off within _KICKOFF_WINDOW_SEC of the fixture."""
    rec = candidates.get(f"{home} vs {away}") or _fuzzy_match_ou25(home, away, candidates)
    if not rec:
        return None
    k, s = _to_ts(kickoff), rec.get("starts_ts")
    if k is not None and s and abs(float(s) - k) > _KICKOFF_WINDOW_SEC:
        return None
    return rec


ou25_for_fixture = entry_for_fixture


_PIN_PAIRS_CACHE = {"ts": 0.0, "pairs": []}
_PAIRS_TTL_SEC = 300.0
_FUZZY_PAIR_THRESHOLD = 0.72  # same bar as _fuzzy_match_ou25


def _fuzzy_resolve_pair(home: str, away: str, kickoff_ts=None):
    """Resolve Betarabia team names to Pinnacle's names when they differ.

    Pinnacle abbreviates ("JJ Urquiza" vs "Justo José de Urquiza", "Barcelona"
    vs "FC Barcelona", "Besiktas" vs "Beşiktaş JK"). The old exact-only lookup
    silently returned None for entire leagues, which read as "Pinnacle does
    not carry this match" — killing the MODEL_VALUE_ALIGN consensus gate for
    ~2/3 of the slate. Mirrors _fuzzy_match_ou25: exact-first, then
    SequenceMatcher on the normalised "home vs away" pair string, threshold
    0.72. Candidate pairs are cached for 5 min (one cheap recent-window
    DISTINCT instead of one per lookup).
    Returns (pin_home, pin_away) or None.
    """
    import time as _time

    now = _time.time()
    if now - _PIN_PAIRS_CACHE["ts"] > _PAIRS_TTL_SEC:
        try:
            con = sqlite3.connect(_COMPLETED_DB, timeout=5)
            try:
                # Recent window only (12h) — upcoming fixtures, and keeps the
                # DISTINCT cheap via idx_soh_ts instead of a 6.9M-row scan.
                pairs = con.execute(
                    "SELECT DISTINCT home_team, away_team FROM sharp_odds_history "
                    "WHERE ts >= ?",
                    (now - 43200.0,),
                ).fetchall()
            finally:
                con.close()
            _PIN_PAIRS_CACHE["ts"] = now
            _PIN_PAIRS_CACHE["pairs"] = [(h, a) for h, a in pairs if h and a]
        except Exception:
            _PIN_PAIRS_CACHE["ts"] = now  # don't hammer on error either

    h_n, a_n = _normalize_team(home), _normalize_team(away)
    query = f"{h_n} vs {a_n}"
    best_score, best = 0.0, None
    for ph, pa in _PIN_PAIRS_CACHE["pairs"]:
        if not _same_level(home, away, ph, pa):
            continue
        if not (_side_ok(home, ph) and _side_ok(away, pa)):
            continue
        candidate = f"{_normalize_team(ph)} vs {_normalize_team(pa)}"
        score = SequenceMatcher(None, query, candidate).ratio()
        if score > best_score:
            best_score, best = score, (ph, pa)
    if best_score >= _FUZZY_PAIR_THRESHOLD:
        return best
    return None


def get_pinnacle_latest(home: str, away: str, selection: str, kickoff_ts=None):
    """
    Return latest Pinnacle snapshot for a match/selection.

    Returns dict with keys: devig_prob, decimal_odds, fair_odds, ts, snapshot_count
    or None if no match found or insufficient snapshots.
    """
    pin_sel = _SEL_MAP.get(selection, selection.lower())
    if not os.path.exists(_COMPLETED_DB):
        return None
    kick = _to_ts(kickoff_ts)

    def _lookup(con, h, a):
        h_norm = _normalize_team(h)
        a_norm = _normalize_team(a)
        where = (
            "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
            "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=? "
        )
        params = [h_norm, a_norm]
        # With a kickoff, only this fixture's rows: the same names also carry
        # youth/reserve games hours earlier, whose prices were being returned.
        if kick is not None:
            where += "AND (starts_ts IS NULL OR starts_ts BETWEEN ? AND ?) "
            params += [kick - _KICKOFF_WINDOW_SEC, kick + _KICKOFF_WINDOW_SEC]
        count_row = con.execute(
            "SELECT COUNT(*) as cnt FROM sharp_odds_history " + where, params
        ).fetchone()
        snapshot_count = count_row["cnt"] if count_row else 0

        row = con.execute(
            "SELECT devig_prob, decimal_odds, ts FROM sharp_odds_history "
            + where
            + "AND selection=? ORDER BY ts DESC LIMIT 1",
            params + [pin_sel],
        ).fetchone()
        if not row:
            return None
        devig_prob = row["devig_prob"]
        if not devig_prob or devig_prob <= 0:
            return None
        return {
            "devig_prob": devig_prob,
            "decimal_odds": row["decimal_odds"],
            "fair_odds": 1.0 / devig_prob,
            "ts": row["ts"],
            "snapshot_count": snapshot_count,
        }

    try:
        con = sqlite3.connect(_COMPLETED_DB, timeout=5)
        con.row_factory = sqlite3.Row

        # 1. Exact normalized names first (old behaviour).
        result = _lookup(con, home, away)

        # 2. Fuzzy fallback (2026-08-31): Pinnacle abbreviates team names;
        #    exact-only was silently dropping ~2/3 of the slate from the
        #    MODEL_VALUE_ALIGN consensus gate.
        if result is None:
            resolved = _fuzzy_resolve_pair(home, away, kickoff_ts)
            if resolved:
                result = _lookup(con, resolved[0], resolved[1])

        con.close()
        return result
    except Exception:
        return None


def check_value(
    home: str,
    away: str,
    selection: str,
    betarabia_odds: float,
    kickoff_ts=None,
    min_edge: float = 0.03,
    min_snapshots: int = 10,
):
    """
    Returns (edge_pct, pinnacle_data) if Betarabia >= Pinnacle fair by min_edge.
    Returns (0.0, None) if no edge, no Pinnacle data, or insufficient snapshots.

    edge_pct > 0 means Betarabia is more generous than Pinnacle fair price.
    min_snapshots: minimum Pinnacle snapshots required for reliable price (P4 FIX).
    """
    if not betarabia_odds or betarabia_odds <= 1.0:
        return 0.0, None

    pin = get_pinnacle_latest(home, away, selection, kickoff_ts)
    if pin is None:
        return 0.0, None

    # P4 FIX: Reject if Pinnacle data is too stale (few snapshots).
    snap_count = pin.get("snapshot_count", 0)
    if snap_count < min_snapshots:
        return 0.0, None

    edge = betarabia_odds / pin["fair_odds"] - 1.0
    if edge >= min_edge:
        return round(edge, 4), pin
    return 0.0, None


def kelly_stake(edge: float, odds: float, kelly_frac: float = 0.2) -> float:
    """
    Fractional Kelly stake as a fraction of bankroll.
    edge = betarabia_odds / fair_odds - 1
    p = fair probability (1/fair_odds)
    Kelly = (p * odds - 1) / (odds - 1) * frac
    """
    if odds <= 1.0 or edge <= 0:
        return 0.0
    # Work backwards: devig_prob = 1 / fair_odds = 1 / (betarabia_odds / (1+edge))
    fair_odds = odds / (1.0 + edge) if edge > 0 else odds
    p = 1.0 / fair_odds
    b = odds - 1.0  # net odds
    k = (p * odds - 1.0) / b
    return max(0.0, min(k * kelly_frac, 0.10))  # cap at 10% bankroll


def check_ou25_value(
    home: str,
    away: str,
    selection: str,
    betarabia_odds: float,
    pinnacle_ou25_data: dict,
    min_edge: float = 0.03,
):
    """
    Returns (edge_pct, pin_data) if Betarabia O/U 2.5 odds beat Pinnacle fair by min_edge.

    pinnacle_ou25_data: dict from fetch_pinnacle_totals() for this match —
      {"over": float, "under": float, "p_over": float, "p_under": float}
    selection: "Over 2.5" or "Under 2.5"
    Returns (0.0, None) if no edge or missing data.
    """
    if not betarabia_odds or betarabia_odds <= 1.0:
        return 0.0, None
    if not pinnacle_ou25_data:
        return 0.0, None

    sel_lower = (selection or "").lower()
    if "over" in sel_lower:
        sel_key = "over"
    elif "under" in sel_lower:
        sel_key = "under"
    else:
        return 0.0, None

    pin_odds = pinnacle_ou25_data.get(sel_key)
    pin_prob = pinnacle_ou25_data.get(f"p_{sel_key}")
    if not pin_odds or not pin_prob or pin_prob <= 0:
        return 0.0, None

    fair_odds = 1.0 / pin_prob
    edge = betarabia_odds / fair_odds - 1.0
    if edge >= min_edge:
        return round(edge, 4), {
            "devig_prob": pin_prob,
            "decimal_odds": pin_odds,
            "fair_odds": round(fair_odds, 4),
        }
    return 0.0, None


def check_btts_value(
    home: str,
    away: str,
    selection: str,
    betarabia_odds: float,
    pinnacle_btts_data: dict,
    min_edge: float = 0.03,
):
    """
    Returns (edge_pct, pin_data) if Betarabia BTTS odds beat Pinnacle fair by min_edge.

    pinnacle_btts_data: dict from fetch_pinnacle_btts() for this match —
      {"yes": float, "no": float, "p_yes": float, "p_no": float}
    selection: "Yes" or "No" (BTTS side)
    Returns (0.0, None) if no edge or missing data.
    """
    if not betarabia_odds or betarabia_odds <= 1.0:
        return 0.0, None
    if not pinnacle_btts_data:
        return 0.0, None

    sel_lower = (selection or "").lower()
    if "yes" in sel_lower:
        sel_key = "yes"
    elif "no" in sel_lower:
        sel_key = "no"
    else:
        return 0.0, None

    pin_odds = pinnacle_btts_data.get(sel_key)
    pin_prob = pinnacle_btts_data.get(f"p_{sel_key}")
    if not pin_odds or not pin_prob or pin_prob <= 0:
        return 0.0, None

    fair_odds = 1.0 / pin_prob
    edge = betarabia_odds / fair_odds - 1.0
    if edge >= min_edge:
        return round(edge, 4), {
            "devig_prob": pin_prob,
            "decimal_odds": pin_odds,
            "fair_odds": round(fair_odds, 4),
        }
    return 0.0, None


def _clv(home, away, pin_sel, entry_odds, kickoff_ts):
    """entry_odds / last Pinnacle price - 1 for this fixture, or None.

    Goes through get_pinnacle_latest(): exact names then fuzzy, and with a
    kickoff only this fixture's rows — Pinnacle lists youth games under the
    senior names, so names alone can return another game's close.
    """
    if not pin_sel or not entry_odds:
        return None
    pin = get_pinnacle_latest(home, away, pin_sel, kickoff_ts)
    if pin is None or not pin["decimal_odds"] or pin["decimal_odds"] <= 1.0:
        return None
    return round(entry_odds / pin["decimal_odds"] - 1.0, 4)


def clv_from_pinnacle_ou25(home: str, away: str, selection: str, entry_odds: float, kickoff_ts=None):
    """CLV for an O/U 2.5 bet ("Over 2.5" / "Under 2.5") against Pinnacle's
    stored over_2.5 / under_2.5 rows. Returns float CLV or None if no data."""
    sel_lower = (selection or "").lower()
    pin_sel = "over_2.5" if "over" in sel_lower else "under_2.5" if "under" in sel_lower else None
    return _clv(home, away, pin_sel, entry_odds, kickoff_ts)


def clv_from_pinnacle_btts(home: str, away: str, selection: str, entry_odds: float, kickoff_ts=None):
    """CLV for a BTTS bet ("Yes" / "No") against Pinnacle's btts_yes / btts_no rows."""
    sel_lower = (selection or "").lower()
    pin_sel = "btts_yes" if "yes" in sel_lower else "btts_no" if "no" in sel_lower else None
    return _clv(home, away, pin_sel, entry_odds, kickoff_ts)


def clv_from_pinnacle(home: str, away: str, selection: str, entry_odds: float, kickoff_ts=None):
    """
    Compute CLV = entry_odds / pinnacle_current_odds - 1.
    Called at settlement time to record how much we beat the closing line.
    Returns float or None.
    """
    return _clv(home, away, _SEL_MAP.get(selection, (selection or "").lower()), entry_odds, kickoff_ts)
