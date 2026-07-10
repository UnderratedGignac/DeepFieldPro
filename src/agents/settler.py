"""
settler.py — SettlerAgent
Grades open bets in bet_log.db using free_results_scraper.
Only settles bets when matches are confirmed FINISHED.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from .base import BaseAgent, TaskResult

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"
MODELS = BASE / "models"


def _normalize_team_name(name: str) -> str:
    """Normalize team name for matching (lowercase, remove common suffixes)."""
    if not name:
        return ""
    import re
    import unicodedata
    
    n = name.lower().strip()
    # Remove accents
    n = "".join(c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn")
    # Remove non-alphanumeric except spaces
    n = re.sub(r"[^a-z0-9\s]", "", n)
    # Remove common suffixes that cause mismatches
    suffixes = ["fc", "cf", "sc", "u23", "pr", "ii", "u20", "united", "city", "rk", "kj"]
    words = [w for w in n.split() if w not in suffixes]
    return " ".join(words)


def _match_teams(bet_match: str, home_team: str, away_team: str) -> Tuple[bool, float]:
    """
    Return (matches, confidence_score) if both team names appear in the bet match string.
    Uses normalized matching with confidence scoring.
    """
    def normalize(s):
        return _normalize_team_name(s)
    
    bet_norm = normalize(bet_match)
    home_norm = normalize(home_team)
    away_norm = normalize(away_team)
    
    # Check direct containment
    home_in_bet = home_norm in bet_norm
    away_in_bet = away_norm in bet_norm
    
    if home_in_bet and away_in_bet:
        return True, 1.0
    
    # Check reversed (away team might be listed first in some sources)
    # Split bet_match to get individual teams
    parts = bet_match.lower().split(" vs ")
    if len(parts) == 2:
        bet_home, bet_away = normalize(parts[0]), normalize(parts[1])
        
        # Normal orientation
        if (home_norm in bet_home or bet_home in home_norm) and \
           (away_norm in bet_away or bet_away in away_norm):
            # Calculate confidence based on similarity
            conf = min(1.0, (len(home_norm) + len(away_norm)) / max(1, len(bet_home) + len(bet_away)))
            return True, conf
        
        # Reversed orientation
        if (home_norm in bet_away or bet_away in home_norm) and \
           (away_norm in bet_home or bet_home in away_norm):
            conf = min(1.0, (len(home_norm) + len(away_norm)) / max(1, len(bet_home) + len(bet_away)))
            return True, conf
    
    # Fuzzy partial match
    score = 0
    if home_norm and any(home_norm in word or word in home_norm for word in bet_norm.split()):
        score += 0.5
    if away_norm and any(away_norm in word or word in away_norm for word in bet_norm.split()):
        score += 0.5
    
    return score >= 1.0, score


def _grade_1x2(home_score: int, away_score: int, selection: str) -> str:
    """Grade a 1X2 bet given the final scores. Returns WIN/LOSS/VOID."""
    if home_score > away_score:
        result = "home"
    elif home_score < away_score:
        result = "away"
    else:
        result = "draw"

    sel_lower = selection.lower()
    if sel_lower in ("home", "1", "h"):
        return "WIN" if result == "home" else "LOSS"
    if sel_lower in ("away", "2", "a"):
        return "WIN" if result == "away" else "LOSS"
    if sel_lower in ("draw", "x", "d"):
        return "WIN" if result == "draw" else "LOSS"
    
    # Unrecognised selection - default to LOSS unless it's a draw and selection was ambiguous
    return "LOSS"


def _grade_over_under(home_score: int, away_score: int, selection: str, line: float) -> str:
    """Grade an Over/Under bet. Returns WIN/LOSS/VOID."""
    total = home_score + away_score
    sel_lower = selection.lower()
    
    if "over" in sel_lower:
        if total > line:
            return "WIN"
        elif total < line:
            return "LOSS"
        else:
            return "VOID"  # Push on exact line
    elif "under" in sel_lower:
        if total < line:
            return "WIN"
        elif total > line:
            return "LOSS"
        else:
            return "VOID"  # Push on exact line
    
    return "LOSS"


def _grade_btts(home_score: int, away_score: int, selection: str) -> str:
    """Grade a BTTS (Both Teams To Score) bet."""
    sel_lower = selection.lower()
    both_scored = home_score > 0 and away_score > 0
    
    if "yes" in sel_lower or "ja" in sel_lower:
        return "WIN" if both_scored else "LOSS"
    elif "no" in sel_lower or "nej" in sel_lower:
        return "WIN" if not both_scored else "LOSS"
    
    return "LOSS"


def _extract_line_from_selection(selection: str) -> Optional[float]:
    """Extract numeric line from selection string (e.g., 'Over 2.5' -> 2.5)."""
    import re
    match = re.search(r'(\d+\.?\d*)', selection)
    if match:
        return float(match.group(1))
    return None


class SettlerAgent(BaseAgent):

    @property
    def agent_card(self) -> dict:
        return {
            "name": "SettlerAgent",
            "version": "2.0.0",
            "description": "Grades open bets via free_results_scraper - only settles FINISHED matches",
        }

    def capabilities(self) -> List[str]:
        return ["bet_grading"]

    def run(self, task: dict) -> TaskResult:
        try:
            date_str = task.get("date")

            # Import free_results_scraper via sys.path trick
            src_path = str(BASE / "src")
            if src_path not in sys.path:
                sys.path.insert(0, src_path)

            try:
                from free_results_scraper import get_finished_results
            except ImportError as ie:
                return TaskResult(
                    success=True,
                    data={"settled": 0, "wins": 0, "losses": 0, "voids": 0},
                    error=f"free_results_scraper import failed: {ie}",
                )

            # Fetch results - free_results_scraper ONLY returns completed matches
            if date_str:
                results_raw = get_finished_results(dates=[date_str])
            else:
                results_raw = get_finished_results()

            # Validate results structure
            results: Dict[str, Tuple[int, int]] = {}
            for key, val in results_raw.items():
                if isinstance(val, (list, tuple)) and len(val) >= 2:
                    try:
                        hs, as_ = int(val[0]), int(val[1])
                        # Sanity check: scores must be non-negative
                        if hs >= 0 and as_ >= 0:
                            results[key] = (hs, as_)
                    except (TypeError, ValueError):
                        continue

            db_path = DATA / "bet_log.db"
            if not db_path.exists():
                return TaskResult(
                    success=True,
                    data={"settled": 0, "wins": 0, "losses": 0, "voids": 0},
                )

            # Read-write connection for updates
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                # CORRECT COLUMN NAMES: bet_id, match_id, side (not id, match, selection)
                rows = conn.execute(
                    """
                    SELECT bet_id, match_id, side, market_type, stake, entry_odds
                    FROM bet_log
                    WHERE result IS NULL OR result = 'OPEN'
                    """
                ).fetchall()

                settled = wins = losses = voids = 0
                settlement_details = []

                for bet in rows:
                    bet_id = bet["bet_id"]
                    bet_match = bet["match_id"] or ""
                    selection = bet["side"] or ""
                    market_type = bet["market_type"] or "1X2"
                    stake = bet["stake"] or 0.0
                    odds = bet["entry_odds"] or 1.0

                    # Try to find a matching result
                    matched_result: Optional[Tuple[int, int]] = None
                    best_confidence = 0.0
                    best_match_name = ""
                    
                    for result_key, (hs, as_) in results.items():
                        # result_key is "Home vs Away"
                        parts = result_key.split(" vs ", 1)
                        if len(parts) != 2:
                            continue
                        home_t, away_t = parts[0].strip(), parts[1].strip()
                        
                        matches, confidence = _match_teams(bet_match, home_t, away_t)
                        if matches and confidence > best_confidence:
                            matched_result = (hs, as_)
                            best_confidence = confidence
                            best_match_name = result_key

                    # Only settle if we found a confident match
                    if matched_result is None or best_confidence < 0.5:
                        continue

                    home_score, away_score = matched_result
                    
                    # Grade based on market type
                    grade = "LOSS"
                    pnl = -stake
                    
                    if market_type == "1X2":
                        grade = _grade_1x2(home_score, away_score, selection)
                    elif "over/under" in market_type.lower() or "over" in selection.lower() or "under" in selection.lower():
                        line = _extract_line_from_selection(selection) or 2.5
                        grade = _grade_over_under(home_score, away_score, selection, line)
                    elif "btts" in market_type.lower() or "both teams" in market_type.lower():
                        grade = _grade_btts(home_score, away_score, selection)
                    else:
                        # Default to 1X2 grading for unknown markets
                        grade = _grade_1x2(home_score, away_score, selection)
                    
                    # Calculate P&L
                    if grade == "WIN":
                        pnl = stake * (odds - 1)
                    elif grade == "VOID":
                        pnl = 0.0
                    else:  # LOSS
                        pnl = -stake

                    # Update database
                    conn.execute(
                        "UPDATE bet_log SET result = ?, pnl = ? WHERE bet_id = ?",
                        (grade, pnl, bet_id),
                    )
                    settled += 1
                    if grade == "WIN":
                        wins += 1
                    elif grade == "LOSS":
                        losses += 1
                    else:
                        voids += 1
                    
                    settlement_details.append({
                        "bet_id": bet_id,
                        "match": best_match_name,
                        "score": f"{home_score}-{away_score}",
                        "grade": grade,
                        "pnl": pnl,
                        "confidence": best_confidence
                    })

                conn.commit()
                
                # Log settlement summary
                if settled > 0:
                    print(f"[SETTLER] Settled {settled} bets: {wins}W / {losses}L / {voids}V")
                    for detail in settlement_details[:10]:  # Log first 10
                        print(f"  {detail['bet_id']}: {detail['match']} ({detail['score']}) -> {detail['grade']} (${detail['pnl']:.2f})")
            finally:
                conn.close()

            return TaskResult(
                success=True,
                data={
                    "settled": settled,
                    "wins": wins,
                    "losses": losses,
                    "voids": voids,
                    "details": settlement_details,
                },
            )

        except Exception as exc:
            import traceback
            return TaskResult(
                success=False,
                error=f"{str(exc)}\n{traceback.format_exc()}",
                data={"settled": 0, "wins": 0, "losses": 0, "voids": 0},
            )
