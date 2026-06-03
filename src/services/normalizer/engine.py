# mypy: ignore-errors
"""
Odds Normalization Engine

Normalizes odds data from different sportsbooks into a consistent format.
Handles market mapping, odds conversion, and data validation.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime


class NormalizationEngine:
    """
    Normalizes odds data from multiple sources into a unified format.

    Features:
    - Market name standardization
    - Odds format conversion (decimal, fractional, american)
    - Data validation and cleaning
    - Arbitrage detection
    """

    def __init__(self):
        self._market_mappings = self._build_market_mappings()
        self._supported_formats = ["decimal", "fractional", "american"]

    def _build_market_mappings(self) -> Dict[str, List[str]]:
        """Build mapping of standard market names to variations."""
        return {
            "1x2": ["match_result", "full_time_result", "1x2", "three_way"],
            "over_under_2.5": [
                "totals_2.5",
                "o/u_2.5",
                "over_under_2.5",
                "total_goals_2.5",
            ],
            "both_teams_to_score": ["btts", "both_teams_score", "gg_ng"],
            "double_chance": ["dc", "double_chance", "1x_12_x2"],
            "asian_handicap": ["ah", "asian_handicap", "handicap"],
            "european_handicap": ["eh", "european_handicap"],
            "correct_score": ["cs", "correct_score", "exact_score"],
            "half_time_full_time": ["ht_ft", "half_full", "ht/ft"],
        }

    def normalize_odds(
        self, raw_odds: Dict[str, Any], source_format: str = "decimal"
    ) -> Dict[str, Any]:
        """
        Normalize raw odds data to standard format.

        Args:
            raw_odds: Raw odds data from sportsbook
            source_format: Format of input odds

        Returns:
            Normalized odds dictionary
        """
        normalized = {
            "fixture_id": raw_odds.get("fixture_id"),
            "sportsbook": raw_odds.get("sportsbook"),
            "timestamp": raw_odds.get("timestamp", datetime.now().isoformat()),
            "markets": {},
        }

        raw_markets = raw_odds.get("markets", {})

        for standard_name, variations in self._market_mappings.items():
            market_data = self._find_market(raw_markets, variations)
            if market_data:
                normalized["markets"][standard_name] = self._normalize_market(
                    market_data, source_format
                )

        return normalized

    def _find_market(self, markets: Dict, variations: List[str]) -> Optional[Dict]:
        """Find market data using known variations."""
        for variation in variations:
            if variation in markets:
                return markets[variation]
            # Case-insensitive search
            for key in markets:
                if key.lower() == variation.lower():
                    return markets[key]
        return None

    def _normalize_market(self, market_data: Dict, source_format: str) -> Dict:
        """Normalize a single market's odds."""
        normalized = {}

        for outcome, odds_value in market_data.items():
            if isinstance(odds_value, (int, float)):
                # Convert to decimal format
                if source_format == "fractional":
                    normalized[outcome] = self._fractional_to_decimal(odds_value)
                elif source_format == "american":
                    normalized[outcome] = self._american_to_decimal(odds_value)
                else:
                    normalized[outcome] = float(odds_value)

        return normalized

    def _fractional_to_decimal(self, fractional: float) -> float:
        """Convert fractional odds to decimal."""
        # Assuming fractional is passed as a decimal representation
        # e.g., 5/2 = 2.5 would be passed as 2.5
        return fractional + 1.0

    def _american_to_decimal(self, american: float) -> float:
        """Convert American odds to decimal."""
        if american > 0:
            return (american / 100) + 1
        else:
            return (100 / abs(american)) + 1

    def validate_odds(self, normalized_odds: Dict) -> bool:
        """
        Validate normalized odds data.

        Checks:
        - All odds are positive
        - No duplicate outcomes
        - Required fields present

        Returns:
            True if valid
        """
        required_fields = ["fixture_id", "sportsbook", "timestamp", "markets"]

        for field in required_fields:
            if field not in normalized_odds:
                return False

        for market_name, market_data in normalized_odds["markets"].items():
            for outcome, odds in market_data.items():
                if odds <= 0:
                    return False

        return True

    def detect_arbitrage(self, odds_from_multiple_books: List[Dict]) -> Optional[Dict]:
        """
        Detect arbitrage opportunities across multiple sportsbooks.

        Args:
            odds_from_multiple_books: List of normalized odds from different books

        Returns:
            Arbitrage opportunity details or None
        """
        if len(odds_from_multiple_books) < 2:
            return None

        # Group by market
        market_odds = {}
        for odds_data in odds_from_multiple_books:
            for market_name, outcomes in odds_data.get("markets", {}).items():
                if market_name not in market_odds:
                    market_odds[market_name] = []
                for outcome, odds in outcomes.items():
                    market_odds[market_name].append(
                        {
                            "sportsbook": odds_data["sportsbook"],
                            "outcome": outcome,
                            "odds": odds,
                        }
                    )

        # Check each market for arbitrage
        for market_name, outcomes in market_odds.items():
            arbitrage = self._check_market_arbitrage(outcomes)
            if arbitrage:
                return arbitrage

        return None

    def _check_market_arbitrage(self, outcomes: List[Dict]) -> Optional[Dict]:
        """Check if a market has arbitrage opportunity."""
        # Group by outcome to get best odds
        best_odds = {}
        for item in outcomes:
            outcome = item["outcome"]
            if outcome not in best_odds or item["odds"] > best_odds[outcome]["odds"]:
                best_odds[outcome] = item

        # Calculate implied probability
        total_implied = sum(1 / item["odds"] for item in best_odds.values())

        if total_implied < 1.0:
            # Arbitrage opportunity exists
            profit_margin = (1.0 - total_implied) * 100
            return {
                "market": outcomes[0].get("market", "unknown"),
                "profit_margin": profit_margin,
                "best_outcomes": best_odds,
                "total_implied_probability": total_implied,
            }

        return None

