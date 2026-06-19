"""
predictor.py — PredictorAgent
Dixon-Coles 1X2 + O/U 2.5 + BTTS predictions with Platt calibration.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseAgent, TaskResult

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"
MODELS = BASE / "models"

# ---------------------------------------------------------------------------
# Module-level caches (loaded once per process)
# ---------------------------------------------------------------------------
_dc_model: Optional[dict] = None
_calib_1x2: Optional[dict] = None
_calib_ou25: Optional[dict] = None


def _load_dc_model() -> dict:
    global _dc_model
    if _dc_model is None:
        path = MODELS / "dixon_coles.json"
        with open(path, "r", encoding="utf-8") as fh:
            _dc_model = json.load(fh)
    return _dc_model


def _load_calib_1x2() -> Optional[dict]:
    global _calib_1x2
    if _calib_1x2 is None:
        path = MODELS / "calibrator_1x2.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                _calib_1x2 = json.load(fh)
    return _calib_1x2


def _load_calib_ou25() -> Optional[dict]:
    global _calib_ou25
    if _calib_ou25 is None:
        path = MODELS / "calibrator_ou25.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                _calib_ou25 = json.load(fh)
    return _calib_ou25


# ---------------------------------------------------------------------------
# Team-name fuzzy match
# ---------------------------------------------------------------------------
_SUFFIXES = {
    "fc",
    "sc",
    "cf",
    "united",
    "city",
    "town",
    "athletic",
    "atletico",
    "sporting",
    "real",
    "club",
}


def _norm(name: str) -> str:
    """Lowercase and strip common suffixes for fuzzy matching."""
    parts = name.lower().split()
    filtered = [p for p in parts if p not in _SUFFIXES]
    return " ".join(filtered).strip()


def _find_team(strengths: dict, name: str) -> Optional[str]:
    """Try exact -> lower -> normalised lookup. Return matched key or None."""
    if name in strengths:
        return name
    lower = name.lower()
    for k in strengths:
        if k.lower() == lower:
            return k
    norm_target = _norm(name)
    if norm_target:
        for k in strengths:
            if _norm(k) == norm_target:
                return k
    return None


# ---------------------------------------------------------------------------
# Poisson helpers
# ---------------------------------------------------------------------------
def _poisson_pmf(lam: float, k: int) -> float:
    """P(X = k) for Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return math.exp(-lam) * (lam**k) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def _dixon_coles_tau(lam_h: float, lam_a: float, rho: float, h: int, a: int) -> float:
    """Dixon-Coles low-score correction factor."""
    if h == 0 and a == 0:
        return 1.0 - lam_h * lam_a * rho
    if h == 0 and a == 1:
        return 1.0 + lam_h * rho
    if h == 1 and a == 0:
        return 1.0 + lam_a * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def _predict_1x2_ou_btts(
    lam_h: float, lam_a: float, rho: float, max_goals: int = 8
) -> Dict[str, float]:
    """Compute 1X2 + O/U 2.5 + BTTS from Poisson lambdas."""
    home_win = draw = away_win = 0.0
    over25 = btts = 0.0

    for h in range(max_goals):
        for a in range(max_goals):
            ph = _poisson_pmf(lam_h, h)
            pa = _poisson_pmf(lam_a, a)
            tau = _dixon_coles_tau(lam_h, lam_a, rho, h, a)
            p = ph * pa * tau
            if p < 0:
                p = 0.0

            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

            if h + a > 2:
                over25 += p
            if h > 0 and a > 0:
                btts += p

    # Normalise 1X2
    total = home_win + draw + away_win
    if total > 0:
        home_win /= total
        draw /= total
        away_win /= total

    return {
        "home_win": round(home_win, 6),
        "draw": round(draw, 6),
        "away_win": round(away_win, 6),
        "over25": round(over25, 6),
        "btts": round(btts, 6),
    }


def _platt_scale(p: float, A: float, B: float) -> float:
    """Platt scaling: 1 / (1 + exp(-(A*p + B)))."""
    try:
        return 1.0 / (1.0 + math.exp(-(A * p + B)))
    except OverflowError:
        return 0.0 if A * p + B < 0 else 1.0


def _calibrate_1x2(home: float, draw: float, away: float) -> tuple:
    calib = _load_calib_1x2()
    if calib is None:
        return home, draw, away
    A = calib.get("A", 1.0)
    B = calib.get("B", 0.0)
    ch = _platt_scale(home, A, B)
    cd = _platt_scale(draw, A, B)
    ca = _platt_scale(away, A, B)
    total = ch + cd + ca
    if total > 0:
        ch /= total
        cd /= total
        ca /= total
    return round(ch, 6), round(cd, 6), round(ca, 6)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class PredictorAgent(BaseAgent):

    @property
    def agent_card(self) -> dict:
        return {
            "name": "PredictorAgent",
            "version": "1.0.0",
            "description": "Dixon-Coles 1X2/OU25/BTTS predictions with calibration",
        }

    def capabilities(self) -> List[str]:
        return ["1x2_prediction", "ou25_prediction"]

    def run(self, task: dict) -> TaskResult:
        try:
            home_name = task.get("home", "")
            away_name = task.get("away", "")
            market_odds = task.get("market_odds", {})

            dc = _load_dc_model()
            strengths = dc.get("team_strengths", {})
            home_adv = dc.get("home_adv", 1.25)
            rho = dc.get("rho", -0.13)

            home_key = _find_team(strengths, home_name)
            away_key = _find_team(strengths, away_name)

            if home_key and away_key:
                hs = strengths[home_key]
                as_ = strengths[away_key]
                lam_h = hs.get("att", 1.0) * as_.get("def", 1.0) * home_adv
                lam_a = as_.get("att", 1.0) * hs.get("def", 1.0)
            else:
                # Fallback heuristic
                lam_h = 1.4
                lam_a = 1.0

            preds = _predict_1x2_ou_btts(lam_h, lam_a, rho)

            # Calibrate 1X2
            cal_h, cal_d, cal_a = _calibrate_1x2(
                preds["home_win"], preds["draw"], preds["away_win"]
            )

            # EV
            ev_home = ev_draw = ev_away = 0.0
            if market_odds.get("home"):
                ev_home = round(cal_h * float(market_odds["home"]) - 1.0, 6)
            if market_odds.get("draw"):
                ev_draw = round(cal_d * float(market_odds["draw"]) - 1.0, 6)
            if market_odds.get("away"):
                ev_away = round(cal_a * float(market_odds["away"]) - 1.0, 6)

            return TaskResult(
                success=True,
                data={
                    "home_win": cal_h,
                    "draw": cal_d,
                    "away_win": cal_a,
                    "over25": preds["over25"],
                    "btts": preds["btts"],
                    "ev_home": ev_home,
                    "ev_draw": ev_draw,
                    "ev_away": ev_away,
                    "lambda_h": round(lam_h, 4),
                    "lambda_a": round(lam_a, 4),
                },
            )

        except Exception as exc:
            return TaskResult(success=False, error=str(exc))
