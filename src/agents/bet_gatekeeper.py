"""
bet_gatekeeper.py — BetGatekeeperAgent
Applies EV filter, conviction cap, and fractional-Kelly sizing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .base import BaseAgent, TaskResult

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"
MODELS = BASE / "models"

_DEFAULTS = {
    "ev_threshold": 0.05,
    "min_confidence": 0.50,
    "edge_cap_pct": 10.0,
    "kelly_multiplier": 0.25,
    "max_stake_pct": 0.05,
    "allowed_markets": ["1X2"],
    "exclude_draws": True,
}


def _devig_market(market_odds: dict) -> Dict[str, float]:
    """Return de-vigged probabilities for home/draw/away."""
    raw = {}
    for k in ("home", "draw", "away"):
        try:
            o = float(market_odds.get(k, 0))
            if o > 0:
                raw[k] = 1.0 / o
        except (TypeError, ValueError):
            pass
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in raw.items()}


class BetGatekeeperAgent(BaseAgent):

    @property
    def agent_card(self) -> dict:
        return {
            "name": "BetGatekeeperAgent",
            "version": "1.0.0",
            "description": "EV filter + conviction cap + Kelly sizing gate",
        }

    def capabilities(self) -> List[str]:
        return ["ev_filter", "kelly_sizing"]

    def run(self, task: dict) -> TaskResult:
        try:
            predictions: dict = task.get("predictions", {})
            market_odds: dict = task.get("market_odds", {})
            bankroll: float = float(task.get("bankroll", 1000.0))
            settings: dict = task.get("settings", {})

            # Merge with defaults
            cfg = {**_DEFAULTS, **settings}
            ev_threshold = float(cfg["ev_threshold"])
            min_confidence = float(cfg["min_confidence"])
            edge_cap_pct = float(cfg["edge_cap_pct"])
            kelly_mult = float(cfg["kelly_multiplier"])
            max_stake_pct = float(cfg["max_stake_pct"])
            allowed_markets = cfg["allowed_markets"]
            exclude_draws = bool(cfg["exclude_draws"])

            # Only 1X2 is handled here; if not in allowed_markets, reject
            if "1X2" not in allowed_markets:
                return TaskResult(
                    success=True,
                    data={
                        "recommended": False,
                        "selection": "",
                        "odds": 0.0,
                        "stake": 0.0,
                        "ev": 0.0,
                        "reason": "1X2 not in allowed_markets",
                    },
                )

            # Build candidate selections
            candidates = []
            ev_map = {
                "home": predictions.get("ev_home", 0.0),
                "draw": predictions.get("ev_draw", 0.0),
                "away": predictions.get("ev_away", 0.0),
            }
            prob_map = {
                "home": predictions.get("home_win", 0.0),
                "draw": predictions.get("draw", 0.0),
                "away": predictions.get("away_win", 0.0),
            }
            for sel in ("home", "draw", "away"):
                if exclude_draws and sel == "draw":
                    continue
                ev = float(ev_map.get(sel, 0.0))
                prob = float(prob_map.get(sel, 0.0))
                odds = float(market_odds.get(sel, 0.0))
                if odds > 0:
                    candidates.append((sel, ev, prob, odds))

            if not candidates:
                return TaskResult(
                    success=True,
                    data={
                        "recommended": False,
                        "selection": "",
                        "odds": 0.0,
                        "stake": 0.0,
                        "ev": 0.0,
                        "reason": "no valid candidates",
                    },
                )

            # Pick best EV candidate
            best = max(candidates, key=lambda x: x[1])
            sel, ev, prob, odds = best

            # EV threshold
            if ev < ev_threshold:
                return TaskResult(
                    success=True,
                    data={
                        "recommended": False,
                        "selection": sel,
                        "odds": odds,
                        "stake": 0.0,
                        "ev": round(ev, 6),
                        "reason": f"EV {ev:.4f} < threshold {ev_threshold}",
                    },
                )

            # Confidence gate
            if prob < min_confidence:
                return TaskResult(
                    success=True,
                    data={
                        "recommended": False,
                        "selection": sel,
                        "odds": odds,
                        "stake": 0.0,
                        "ev": round(ev, 6),
                        "reason": f"prob {prob:.4f} < min_confidence {min_confidence}",
                    },
                )

            # Conviction cap: if model prob disagrees with de-vigged market too much, skip
            devigged = _devig_market(market_odds)
            market_prob = devigged.get(sel, 0.0)
            if market_prob > 0 and (prob - market_prob) > (edge_cap_pct / 100.0):
                return TaskResult(
                    success=True,
                    data={
                        "recommended": False,
                        "selection": sel,
                        "odds": odds,
                        "stake": 0.0,
                        "ev": round(ev, 6),
                        "reason": (
                            f"conviction cap breached: model {prob:.4f} "
                            f"vs market {market_prob:.4f} "
                            f"> {edge_cap_pct}%"
                        ),
                    },
                )

            # Kelly stake
            if odds > 1:
                kelly_stake = kelly_mult * ev / (odds - 1.0) * bankroll
            else:
                kelly_stake = 0.0
            max_stake = max_stake_pct * bankroll
            stake = round(min(max(kelly_stake, 0.0), max_stake), 2)

            return TaskResult(
                success=True,
                data={
                    "recommended": True,
                    "selection": sel,
                    "odds": odds,
                    "stake": stake,
                    "ev": round(ev, 6),
                    "reason": "passed all gates",
                },
            )

        except Exception as exc:
            return TaskResult(success=False, error=str(exc))
