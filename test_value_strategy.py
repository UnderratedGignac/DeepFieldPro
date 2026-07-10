"""
Comprehensive Tests for Value Strategy Agent
Tests Kelly Criterion, Edge Calculation, and Risk Management
"""

import unittest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agents.value_strategy import ValueStrategyAgent, ValueBet

class TestValueStrategy(unittest.TestCase):
    
    def setUp(self):
        self.agent = ValueStrategyAgent(bankroll=1000.0, kelly_fraction=0.25, min_edge=0.05)
        
    def test_implied_probability_calculation(self):
        """Test converting odds to implied probability"""
        # Even money (2.0) = 50%
        self.assertAlmostEqual(self.agent.calculate_implied_probability(2.0), 0.50)
        # Heavy favorite (1.25) = 80%
        self.assertAlmostEqual(self.agent.calculate_implied_probability(1.25), 0.80)
        # Underdog (4.0) = 25%
        self.assertAlmostEqual(self.agent.calculate_implied_probability(4.0), 0.25)
        # Invalid odds
        self.assertEqual(self.agent.calculate_implied_probability(0.5), 1.0)
        
    def test_kelly_criterion_stake_calculation(self):
        """Test Fractional Kelly stake sizing"""
        # Scenario: 60% chance to win at 2.0 odds
        # Full Kelly: (1.0 * 0.6 - 0.4) / 1.0 = 0.2 (20% of bankroll)
        # Quarter Kelly: 20% * 0.25 = 5% of bankroll = $50
        stake = self.agent.calculate_optimal_stake(model_prob=0.60, odds=2.0)
        self.assertAlmostEqual(stake, 50.0, places=1)
        
        # Scenario: 40% chance to win at 3.0 odds (Fair bet, no edge)
        # Edge = (0.4 * 3.0) - 1 = 0.2 (Positive!)
        # Full Kelly: (2.0 * 0.4 - 0.6) / 2.0 = 0.1 (10%)
        # Quarter Kelly: 2.5% = $25
        stake = self.agent.calculate_optimal_stake(model_prob=0.40, odds=3.0)
        self.assertAlmostEqual(stake, 25.0, places=1)
        
        # Negative EV bet should return 0
        # 30% chance at 2.0 odds -> Edge = -0.4
        stake = self.agent.calculate_optimal_stake(model_prob=0.30, odds=2.0)
        self.assertEqual(stake, 0.0)
        
    def test_edge_calculation_logic(self):
        """Test that edge is calculated correctly"""
        match = {
            'id': 'test1',
            'home_team': 'Team A',
            'away_team': 'Team B',
            'odds_home': 2.0
        }
        predictions = {'1X2_Home': 0.55} # Model says 55%, Odds imply 50%
        
        # Edge = (0.55 * 2.0) - 1 = 0.10 (10%)
        bet = self.agent.analyze_match(match, predictions)
        
        self.assertIsNotNone(bet)
        self.assertGreater(bet.edge, 0.05) # Above threshold
        self.assertAlmostEqual(bet.edge, 0.10, places=2)
        
    def test_no_bet_below_threshold(self):
        """Ensure no bets are placed if edge is below minimum"""
        match = {
            'id': 'test2',
            'home_team': 'Team A',
            'away_team': 'Team B',
            'odds_home': 2.0
        }
        # Model says 52%, Odds imply 50%. Edge = 4% (Below 5% threshold)
        predictions = {'1X2_Home': 0.52}
        
        bet = self.agent.analyze_match(match, predictions)
        self.assertIsNone(bet)
        
    def test_max_stake_cap(self):
        """Ensure stake never exceeds 5% of bankroll regardless of Kelly"""
        # Extreme scenario: 90% chance at 1.5 odds
        # Full Kelly would be huge, but we cap at 5%
        stake = self.agent.calculate_optimal_stake(model_prob=0.90, odds=1.5)
        max_allowed = 1000.0 * 0.05
        
        self.assertLessEqual(stake, max_allowed)
        
    def test_multiple_markets_best_edge_selection(self):
        """Test that agent picks the market with highest edge"""
        match = {
            'id': 'test3',
            'home_team': 'Team A',
            'away_team': 'Team B',
            'odds_home': 2.0,      # Model 55% -> Edge 10%
            'odds_over_2.5': 1.80, # Model 70% -> Edge 26% (Best)
            'odds_btts_yes': 1.90  # Model 55% -> Edge 4.5% (Below threshold)
        }
        predictions = {
            '1X2_Home': 0.55,
            'OU_Over_2.5': 0.70,
            'BTTS_Yes': 0.55
        }
        
        bet = self.agent.analyze_match(match, predictions)
        
        self.assertIsNotNone(bet)
        self.assertEqual(bet.market, 'Over/Under 2.5')
        self.assertEqual(bet.selection, 'Over')
        self.assertGreater(bet.edge, 0.20)
        
    def test_generate_bets_sorting(self):
        """Test that generated bets are sorted by edge descending"""
        matches = [
            {
                'id': 'm1', 'home_team': 'A', 'away_team': 'B',
                'odds_home': 2.0 # 60% model -> 20% edge
            },
            {
                'id': 'm2', 'home_team': 'C', 'away_team': 'D',
                'odds_home': 2.0 # 55% model -> 10% edge
            }
        ]
        predictions = {
            'm1': {'1X2_Home': 0.60},
            'm2': {'1X2_Home': 0.55}
        }
        
        bets = self.agent.generate_bets(matches, predictions)
        
        self.assertEqual(len(bets), 2)
        self.assertGreater(bets[0].edge, bets[1].edge)
        
    def test_bankroll_management_integration(self):
        """Test that stakes adjust when bankroll changes"""
        agent_small = ValueStrategyAgent(bankroll=100.0, kelly_fraction=0.25)
        agent_large = ValueStrategyAgent(bankroll=10000.0, kelly_fraction=0.25)
        
        match = {'id': 'x', 'home_team': 'A', 'away_team': 'B', 'odds_home': 2.0}
        preds = {'1X2_Home': 0.60}
        
        bet_small = agent_small.analyze_match(match, preds)
        bet_large = agent_large.analyze_match(match, preds)
        
        # Large bankroll stake should be roughly 100x small bankroll stake
        # (unless capped by 5% rule, so we check ratio is reasonable)
        self.assertGreater(bet_large.recommended_stake, bet_small.recommended_stake)

if __name__ == '__main__':
    print("Running Value Strategy Tests...")
    unittest.main(verbosity=2)
