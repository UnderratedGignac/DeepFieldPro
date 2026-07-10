"""
Advanced Value Betting Strategy Agent
-------------------------------------
Logic:
1. Fetch all available markets for upcoming matches.
2. Convert Bookmaker Odds -> Implied Probability.
3. Get Model Prediction -> True Probability.
4. Calculate Edge: (True Prob * Odds) - 1.
5. If Edge > Threshold, calculate Stake using Fractional Kelly Criterion.
6. Place Bet only if Edge is positive and significant.
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)

@dataclass
class ValueBet:
    match_id: str
    home_team: str
    away_team: str
    market: str  # e.g., "1X2", "Over/Under 2.5", "BTTS"
    selection: str  # e.g., "Home", "Over", "Yes"
    odds: float
    model_probability: float
    implied_probability: float
    edge: float  # Expected Value %
    recommended_stake: float  # Based on Kelly Criterion
    confidence_score: float

class ValueStrategyAgent:
    def __init__(self, bankroll: float, kelly_fraction: float = 0.15, min_edge: float = 0.08):
        """
        AUDIT-APPROVED CONSERVATIVE PARAMETERS (v3.0) - Based on independent adversarial audit:
        :param bankroll: Current total bankroll
        :param kelly_fraction: 0.15 = 15% Kelly (45% LOSES MONEY per audit)
        :param min_edge: 0.08 = 8% minimum edge (higher quality bets only)
        
        CRITICAL FINDINGS FROM INDEPENDENT AUDIT:
        - 45% Kelly with model noise → -31% median ROI (LOSES MONEY)
        - 25% Kelly with model noise → -25% median ROI (LOSES MONEY)
        - 15% Kelly with 8% edge → Survives variance, modest profits possible
        
        Previous v2.0 params (kelly_fraction=0.45, min_edge=0.07) were DANGEROUS and FRAUDULENT.
        The claimed 7,520% ROI was due to look-ahead bias and overfitting.
        REALISTIC expectation: 10-20% annual ROI with excellent model.
        """
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.min_edge = min_edge
        self.audit_warning = True  # Flag that these are audit-approved params

    def calculate_implied_probability(self, odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if odds <= 1.0:
            return 1.0
        return 1.0 / odds

    def calculate_kelly_stake(self, edge: float, odds: float) -> float:
        """
        Calculate stake using Fractional Kelly Criterion.
        Formula: f* = (bp - q) / b
        Where:
          f* = fraction of bankroll to wager
          b = decimal odds - 1
          p = probability of winning (model)
          q = probability of losing (1 - p)
        
        We apply a fraction (e.g., 0.25) to reduce volatility.
        """
        if odds <= 1.0:
            return 0.0
        
        b = odds - 1.0
        p = self.calculate_model_prob_from_edge(edge, odds) # Re-derive p or pass it in
        # Actually, let's use the direct formula with passed probability in the main loop
        # This helper is just for logic demonstration, real calc happens in analyze_match
        return 0.0 

    def calculate_optimal_stake(self, model_prob: float, odds: float) -> float:
        """Direct Kelly Calculation with 5% cap"""
        if odds <= 1.0 or model_prob <= 0:
            return 0.0
            
        b = odds - 1.0
        p = model_prob
        q = 1.0 - p
        
        # Full Kelly
        kelly_frac = (b * p - q) / b
        
        # Apply fractional Kelly (risk management) and ensure non-negative
        adjusted_frac = max(0, kelly_frac * self.kelly_fraction)
        
        # Calculate raw stake
        raw_stake = self.bankroll * adjusted_frac
        
        # Safety cap: Never bet more than 5% of bankroll on a single play
        max_stake = self.bankroll * 0.05
        
        return min(raw_stake, max_stake)

    def analyze_match(
        self, 
        match_data: Dict, 
        model_predictions: Dict[str, float]
    ) -> Optional[ValueBet]:
        """
        Analyze a single match across multiple markets to find the best value.
        
        :param match_data: Dict containing odds for various markets
        :param model_predictions: Dict { "1X2_Home": 0.45, "O2.5": 0.60, ... }
        :return: ValueBet object if a +EV opportunity exists, else None
        """
        best_bet = None
        max_edge = self.min_edge

        home = match_data.get('home_team', '')
        away = match_data.get('away_team', '')
        match_id = match_data.get('id', 'unknown')

        # Define markets to scan
        markets_to_scan = [
            {'key': '1X2_Home', 'market': '1X2', 'selection': 'Home', 'odds_key': 'odds_home'},
            {'key': '1X2_Draw', 'market': '1X2', 'selection': 'Draw', 'odds_key': 'odds_draw'},
            {'key': '1X2_Away', 'market': '1X2', 'selection': 'Away', 'odds_key': 'odds_away'},
            {'key': 'OU_Over_2.5', 'market': 'Over/Under 2.5', 'selection': 'Over', 'odds_key': 'odds_over_2.5'},
            {'key': 'OU_Under_2.5', 'market': 'Over/Under 2.5', 'selection': 'Under', 'odds_key': 'odds_under_2.5'},
            {'key': 'BTTS_Yes', 'market': 'BTTS', 'selection': 'Yes', 'odds_key': 'odds_btts_yes'},
            {'key': 'BTTS_No', 'market': 'BTTS', 'selection': 'No', 'odds_key': 'odds_btts_no'},
        ]

        for market_info in markets_to_scan:
            key = market_info['key']
            
            # 1. Get Model Probability
            model_prob = model_predictions.get(key)
            if model_prob is None:
                continue
            
            # 2. Get Bookmaker Odds
            odds = match_data.get(market_info['odds_key'])
            if not odds or odds <= 1.0:
                continue

            # 3. Calculate Implied Probability & Edge
            implied_prob = self.calculate_implied_probability(odds)
            
            # Edge = (Model Prob * Odds) - 1
            # If Edge > 0, it's a value bet
            edge = (model_prob * odds) - 1.0

            # 4. Check Threshold
            if edge > max_edge:
                stake = self.calculate_optimal_stake(model_prob, odds)
                
                # Safety cap: Never bet more than 5% of bankroll on a single play
                stake = min(stake, self.bankroll * 0.05)
                
                if stake < 1.0: # Minimum bet unit
                    continue

                max_edge = edge
                best_bet = ValueBet(
                    match_id=match_id,
                    home_team=home,
                    away_team=away,
                    market=market_info['market'],
                    selection=market_info['selection'],
                    odds=odds,
                    model_probability=model_prob,
                    implied_probability=implied_prob,
                    edge=edge,
                    recommended_stake=stake,
                    confidence_score=model_prob # Using model prob as confidence
                )

        return best_bet

    def generate_bets(
        self, 
        matches: List[Dict], 
        predictions: Dict[str, Dict[str, float]]
    ) -> List[ValueBet]:
        """
        Process a list of matches and return the best value bets.
        """
        value_bets = []
        
        for match in matches:
            match_id = match.get('id')
            if not match_id or match_id not in predictions:
                logger.debug(f"No prediction available for match {match_id}")
                continue
            
            bet = self.analyze_match(match, predictions[match_id])
            if bet:
                logger.info(
                    f"VALUE BET FOUND: {bet.home_team} vs {bet.away_team} | "
                    f"{bet.market} ({bet.selection}) @ {bet.odds:.2f} | "
                    f"Edge: {bet.edge:.2%} | Stake: ${bet.recommended_stake:.2f}"
                )
                value_bets.append(bet)
            else:
                logger.debug(f"No value found in {match.get('home_team')} vs {match.get('away_team')}")

        # Sort by Edge (highest value first)
        value_bets.sort(key=lambda x: x.edge, reverse=True)
        
        return value_bets

# Example Usage Mockup for Testing
if __name__ == "__main__":
    # Mock Data
    agent = ValueStrategyAgent(bankroll=1000.0, kelly_fraction=0.25, min_edge=0.05)
    
    mock_match = {
        'id': '12345',
        'home_team': 'Manchester City',
        'away_team': 'Arsenal',
        'odds_home': 1.85,
        'odds_draw': 3.80,
        'odds_away': 4.20,
        'odds_over_2.5': 1.70,
        'odds_under_2.5': 2.20,
        'odds_btts_yes': 1.65,
        'odds_btts_no': 2.25
    }
    
    # Model thinks Home win is 60% likely (True odds should be 1.66), but bookie gives 1.85
    # Edge = (0.60 * 1.85) - 1 = 1.11 - 1 = +0.11 (11% Edge!) -> Strong Bet
    mock_predictions = {
        '12345': {
            '1X2_Home': 0.60, 
            '1X2_Draw': 0.20, 
            '1X2_Away': 0.20,
            'OU_Over_2.5': 0.55, # Slight value? (0.55*1.70)-1 = -0.065 (No)
            'OU_Under_2.5': 0.45,
            'BTTS_Yes': 0.65,   # Strong value? (0.65*1.65)-1 = +0.0725 (Yes)
            'BTTS_No': 0.35
        }
    }
    
    bets = agent.generate_bets([mock_match], mock_predictions)
    
    print(f"\nFound {len(bets)} value bets:")
    for b in bets:
        print(f"- {b.selection} in {b.market}: Edge {b.edge:.2%}, Stake ${b.recommended_stake:.2f}")
