"""
match_simulator.py — DeepFieldPro Monte Carlo Simulation Engine
================================================================
Simulates a match N times (default 10,000) by:
  1. Drawing player-level events (goals, assists, shots, cards) using Poisson / Binomial distributions
  2. Aggregating player draws to team-level outcomes
  3. Computing match result probabilities, exact scorelines, Over/Under, BTTS

BUG FIXES vs previous version:
  - xg/xa/shots are per-90 values → converted to per-match using expected_minutes (default 75)
  - anytime_goal now derived from simulation (np.mean(goals > 0)), not from raw input
  - All player prop output values rounded to 1 decimal place
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any
import json


class MatchSimulator:
    """
    Monte Carlo Simulation Engine for DeepFieldPro.
    Simulates a match N times by resolving player-level events
    into team-level outcomes, then into match-level outcomes.
    """

    def __init__(self, num_simulations: int = 10000):
        self.n_sims = num_simulations

    def _poisson(self, lam: float) -> np.ndarray:
        """Draw Poisson samples, clamping lam to >=0 to be safe."""
        return np.random.poisson(max(lam, 0.0), self.n_sims)

    def _binomial(self, p: float) -> np.ndarray:
        """Draw Bernoulli samples, clamping p to [0,1]."""
        return np.random.binomial(1, min(max(p, 0.0), 1.0), self.n_sims)

    def simulate_player(self, player: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """
        Simulate a single player's actions over self.n_sims matches.

        Player dict fields (all p90 rates):
          name          str  - player name
          xg_p90        float - expected goals per 90 min  (FIXED: was mislabelled xg)
          xa_p90        float - expected assists per 90 min
          shots_p90     float - shots per 90 min
          yellow_p90    float - yellow cards per 90 min
          expected_minutes int - expected minutes in this specific match (default 75)
        """
        # BUG FIX 1: Convert p90 rates → per-match rates using expected_minutes
        mins = float(player.get("expected_minutes", 75))
        scale = mins / 90.0

        xg_match = player.get("xg_p90", player.get("xg", 0.0)) * scale
        xa_match = player.get("xa_p90", player.get("xa", 0.0)) * scale
        shots_match = player.get("shots_p90", player.get("shots", 0.0)) * scale
        # Cards modelled as per-game probability (already a rate, not p90)
        yellow_prob = min(
            player.get("yellow_p90", player.get("yellow_prob", 0.0)) * scale, 0.99
        )

        return {
            "goals": self._poisson(xg_match),
            "assists": self._poisson(xa_match),
            "shots": self._poisson(shots_match),
            "yellow_cards": self._binomial(yellow_prob),
        }

    def simulate_match(
        self,
        home_players: List[Dict],
        away_players: List[Dict],
        match_context: Dict,
    ) -> Dict[str, Any]:
        """
        Run the full match simulation.
          1. Simulate all players
          2. Aggregate to team goals
          3. Compute match outcomes
          4. Return full JSON-ready report
        """
        home_goals = np.zeros(self.n_sims, dtype=int)
        away_goals = np.zeros(self.n_sims, dtype=int)

        home_player_results = []
        for p in home_players:
            sims = self.simulate_player(p)
            home_goals += sims["goals"]
            home_player_results.append(self._player_output(p["name"], sims))

        away_player_results = []
        for p in away_players:
            sims = self.simulate_player(p)
            away_goals += sims["goals"]
            away_player_results.append(self._player_output(p["name"], sims))

        # ── Match outcome calculations ──────────────────────────────────────
        n = self.n_sims
        home_wins = int(np.sum(home_goals > away_goals))
        draws = int(np.sum(home_goals == away_goals))
        away_wins = int(np.sum(home_goals < away_goals))

        total_goals = home_goals + away_goals
        over_25 = int(np.sum(total_goals > 2.5))
        over_15 = int(np.sum(total_goals > 1.5))
        over_35 = int(np.sum(total_goals > 3.5))
        btts_yes = int(np.sum((home_goals > 0) & (away_goals > 0)))

        # Exact score distribution (cap individual goals at 7 for display)
        scores = [f"{min(h, 7)}-{min(a, 7)}" for h, a in zip(home_goals, away_goals)]
        score_series = pd.Series(scores).value_counts(normalize=True) * 100
        most_likely_scores = [
            {"score": k, "probability": round(float(v), 1)}
            for k, v in score_series.head(8).items()
        ]

        return {
            "match": f"{match_context['home_team']} vs {match_context['away_team']}",
            "home_win": round(home_wins / n * 100, 1),
            "draw": round(draws / n * 100, 1),
            "away_win": round(away_wins / n * 100, 1),
            "expected_goals": {
                "home": round(float(np.mean(home_goals)), 2),
                "away": round(float(np.mean(away_goals)), 2),
            },
            "most_likely_scores": most_likely_scores,
            "markets": {
                "over_1_5": round(over_15 / n * 100, 1),
                "under_1_5": round((1 - over_15 / n) * 100, 1),
                "over_2_5": round(over_25 / n * 100, 1),
                "under_2_5": round((1 - over_25 / n) * 100, 1),
                "over_3_5": round(over_35 / n * 100, 1),
                "under_3_5": round((1 - over_35 / n) * 100, 1),
                "btts_yes": round(btts_yes / n * 100, 1),
                "btts_no": round((1 - btts_yes / n) * 100, 1),
            },
            "player_props": home_player_results + away_player_results,
        }

    @staticmethod
    def _player_output(name: str, sims: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """
        Build the player props output dict from simulation arrays.
        BUG FIX 2: anytime_goal now derived from simulation, not from raw input.
        BUG FIX 3: All values rounded to 1 decimal place.
        """
        return {
            "player": name,
            # BUG FIX 2: use mean(goals > 0) from the simulation, not a static input prob
            "anytime_goal": round(float(np.mean(sims["goals"] > 0)) * 100, 1),
            "assist": round(float(np.mean(sims["assists"] > 0)) * 100, 1),
            "shots_1plus": round(float(np.mean(sims["shots"] > 0)) * 100, 1),
            "shots_2plus": round(float(np.mean(sims["shots"] > 1)) * 100, 1),
            "yellow_card": round(float(np.mean(sims["yellow_cards"] > 0)) * 100, 1),
        }


if __name__ == "__main__":
    # ── Self-test with realistic per-90 values ──────────────────────────────
    simulator = MatchSimulator(num_simulations=10000)

    home = [
        # Striker: ~0.5 xG/90, 3 shots/90, 75 mins expected
        {
            "name": "Morata",
            "xg_p90": 0.50,
            "xa_p90": 0.10,
            "shots_p90": 3.0,
            "yellow_p90": 0.15,
            "expected_minutes": 75,
        },
        # Winger: ~0.25 xG/90, 2 shots/90
        {
            "name": "Williams",
            "xg_p90": 0.25,
            "xa_p90": 0.30,
            "shots_p90": 2.0,
            "yellow_p90": 0.10,
            "expected_minutes": 80,
        },
        # CM: ~0.08 xG/90, 1 shot/90
        {
            "name": "Pedri",
            "xg_p90": 0.08,
            "xa_p90": 0.25,
            "shots_p90": 1.0,
            "yellow_p90": 0.20,
            "expected_minutes": 90,
        },
    ]
    away = [
        {
            "name": "Firmino",
            "xg_p90": 0.35,
            "xa_p90": 0.15,
            "shots_p90": 2.5,
            "yellow_p90": 0.12,
            "expected_minutes": 70,
        },
        {
            "name": "Fred",
            "xg_p90": 0.05,
            "xa_p90": 0.10,
            "shots_p90": 0.8,
            "yellow_p90": 0.30,
            "expected_minutes": 90,
        },
    ]
    ctx = {"home_team": "Spain", "away_team": "Brazil"}

    result = simulator.simulate_match(home, away, ctx)
    print(json.dumps(result, indent=2))
