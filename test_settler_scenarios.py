"""
Comprehensive Test Scenarios for the Betting Settler Agent.
Tests cover:
1. The "Early Settlement" Bug (Matches not finished)
2. Correct P&L Calculation (Win/Loss/Void)
3. Market Logic (1X2, Over/Under, BTTS)
4. Team Name Normalization & Confidence Scoring
5. Data Validation & Safety Checks
"""

import sys
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from typing import NamedTuple

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Mock free_results_scraper BEFORE importing settler (it tries to import it on module load)
mock_scraper = MagicMock()
sys.modules['free_results_scraper'] = mock_scraper

# Import the settler module directly
from agents.settler import (
    SettlerAgent, 
    _normalize_team_name, 
    _match_teams, 
    _grade_1x2, 
    _grade_over_under, 
    _grade_btts,
    _extract_line_from_selection
)

class MockBetRecord(NamedTuple):
    """Mock bet record matching SQLite row structure."""
    bet_id: int
    match_id: str
    side: str
    market_type: str
    stake: float
    entry_odds: float

def create_mock_bet_row(
    bet_id: int,
    match_id: str,
    side: str,
    market_type: str = "1X2",
    stake: float = 100.0,
    entry_odds: float = 2.0
):
    """Helper to create a mock bet row (as returned by SQLite)."""
    return MockBetRecord(
        bet_id=bet_id,
        match_id=match_id,
        side=side,
        market_type=market_type,
        stake=stake,
        entry_odds=entry_odds
    )

class TestScenarios:
    def __init__(self):
        self.agent = SettlerAgent()
        self.results = []

    def log(self, test_name: str, passed: bool, details: str = ""):
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n{status}: {test_name}")
        if details:
            print(f"   -> {details}")
        self.results.append((test_name, passed, details))

    # ------------------------------------------------------------------
    # UNIT TESTS: Helper Functions
    # ------------------------------------------------------------------
    
    def test_normalize_team_name(self):
        """Test team name normalization logic."""
        tests = [
            ("Manchester United FC", "manchester united"),
            ("Man United", "man united"),
            ("Liverpool", "liverpool"),
            ("Real Madrid CF", "real madrid"),
            ("Bayer Leverkusen U23", "bayer leverkusen"),
        ]
        all_passed = True
        for input_name, expected in tests:
            result = _normalize_team_name(input_name)
            if expected not in result and result not in expected:
                all_passed = False
                self.log(f"Normalize '{input_name}'", False, f"Got '{result}', expected contains '{expected}'")
        
        if all_passed:
            self.log("Team Name Normalization", True, "All normalizations correct")

    def test_match_teams_confidence(self):
        """Test team matching with confidence scoring."""
        # Perfect match
        matches, conf = _match_teams("Man United vs Liverpool", "Manchester United", "Liverpool")
        if not (matches and conf >= 0.5):
            self.log("Match Teams (Perfect)", False, f"Expected match with conf>=0.5, got {matches}, {conf}")
        else:
            # Test partial match
            matches2, conf2 = _match_teams("Man Utd vs Liverpool", "Manchester United FC", "Liverpool")
            if matches2 and conf2 >= 0.5:
                self.log("Match Teams Confidence Scoring", True, f"Confidence: {conf}")
            else:
                self.log("Match Teams Confidence Scoring", False, f"Partial match failed: {matches2}, {conf2}")

    def test_grade_1x2(self):
        """Test 1X2 grading logic."""
        # Home win
        assert _grade_1x2(2, 0, "Home") == "WIN"
        assert _grade_1x2(2, 0, "1") == "WIN"
        # Away win
        assert _grade_1x2(0, 2, "Away") == "WIN"
        assert _grade_1x2(0, 2, "2") == "WIN"
        # Draw
        assert _grade_1x2(1, 1, "Draw") == "WIN"
        assert _grade_1x2(1, 1, "X") == "WIN"
        # Losses
        assert _grade_1x2(0, 1, "Home") == "LOSS"
        assert _grade_1x2(1, 0, "Away") == "LOSS"
        assert _grade_1x2(1, 1, "Home") == "LOSS"
        self.log("1X2 Grading Logic", True, "All 1X2 cases correct")

    def test_grade_over_under(self):
        """Test Over/Under grading logic."""
        # Over 2.5 - Win (3 goals)
        assert _grade_over_under(2, 1, "Over 2.5", 2.5) == "WIN"
        # Over 2.5 - Loss (1 goal)
        assert _grade_over_under(1, 0, "Over 2.5", 2.5) == "LOSS"
        # Over 2.0 - Push (exactly 2 goals)
        assert _grade_over_under(1, 1, "Over 2.0", 2.0) == "VOID"
        # Under 2.5 - Win (1 goal)
        assert _grade_over_under(1, 0, "Under 2.5", 2.5) == "WIN"
        # Under 2.5 - Loss (3 goals)
        assert _grade_over_under(2, 1, "Under 2.5", 2.5) == "LOSS"
        self.log("Over/Under Grading Logic", True, "All O/U cases correct including push")

    def test_grade_btts(self):
        """Test BTTS grading logic."""
        # Both scored - Yes wins
        assert _grade_btts(2, 1, "Yes") == "WIN"
        assert _grade_btts(1, 1, "Yes") == "WIN"
        # Clean sheet - No wins
        assert _grade_btts(1, 0, "No") == "WIN"
        assert _grade_btts(0, 2, "No") == "WIN"
        # Both scored - No loses
        assert _grade_btts(2, 1, "No") == "LOSS"
        self.log("BTTS Grading Logic", True, "All BTTS cases correct")

    def test_extract_line(self):
        """Test line extraction from selection strings."""
        assert _extract_line_from_selection("Over 2.5") == 2.5
        assert _extract_line_from_selection("Under 1.75") == 1.75
        assert _extract_line_from_selection("Over 3") == 3.0
        assert _extract_line_from_selection("Yes") is None
        self.log("Line Extraction", True, "All line extractions correct")

    # ------------------------------------------------------------------
    # INTEGRATION TESTS: Full Settlement Flow
    # ------------------------------------------------------------------
    
    def _create_temp_db(self, bets: list):
        """Create a temporary SQLite DB with test bets."""
        fd, path = tempfile.mkstemp(suffix=".db")
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE bet_log (
                bet_id INTEGER PRIMARY KEY,
                match_id TEXT,
                side TEXT,
                market_type TEXT,
                stake REAL,
                entry_odds REAL,
                result TEXT,
                pnl REAL
            )
        """)
        for bet in bets:
            conn.execute(
                "INSERT INTO bet_log (bet_id, match_id, side, market_type, stake, entry_odds, result, pnl) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (bet.bet_id, bet.match_id, bet.side, bet.market_type, bet.stake, bet.entry_odds, None, None)
            )
        conn.commit()
        conn.close()
        return path

    def test_early_settlement_prevention(self):
        """
        BUG REPRODUCTION: Ensure bets are NOT settled if match is not in finished results.
        The free_results_scraper only returns COMPLETED matches.
        If a match is HT or Live, it won't be in results, so bet should stay pending.
        """
        bet = create_mock_bet_row(1, "Man United vs Liverpool", "Home", "1X2", 100.0, 2.0)
        db_path = self._create_temp_db([bet])
        
        # Mock results that DON'T include our match (simulating HT/Live match)
        mock_results = {
            "Chelsea vs Arsenal": (2, 1),  # Different match
        }
        
        try:
            import agents.settler as settler_module
            original_data = settler_module.DATA
            original_data = settler_module.DATA
            settler_module.DATA = Path(db_path).parent
            
            with patch('free_results_scraper.get_finished_results', return_value=mock_results):
                result = self.agent.run({})
                
                # Check DB - bet should still be pending
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT result FROM bet_log WHERE bet_id = 1").fetchone()
                conn.close()
                
                passed = row[0] is None  # Should still be NULL
                self.log(
                    "Prevent Early Settlement (Match Not In Results)", 
                    passed, 
                    f"Result in DB: {row[0]} (should be NULL)"
                )
            
            settler_module.DATA = original_data
        finally:
            os.unlink(db_path)

    def test_correct_win_settlement(self):
        """Verify P&L calculation for a winning bet."""
        # Bet: Home Win @ 2.5, Stake 100. Expected Profit: 150
        bet = create_mock_bet_row(2, "Man United vs Liverpool", "Home", "1X2", 100.0, 2.5)
        db_path = self._create_temp_db([bet])
        
        mock_results = {
            "Man United vs Liverpool": (2, 0),  # Home wins
        }
        
        import agents.settler as settler_module
        
        try:
            original_data = settler_module.DATA
            settler_module.DATA = Path(db_path).parent
            
            with patch('free_results_scraper.get_finished_results', return_value=mock_results):
                result = self.agent.run({})
                
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT result, pnl FROM bet_log WHERE bet_id = 2").fetchone()
                conn.close()
                
                passed = (row[0] == "WIN" and row[1] == 150.0)
                self.log("Correct Win Calculation (1X2)", passed, f"Status: {row[0]}, PnL: {row[1]} (Expected WIN, 150.0)")
        finally:
            settler_module.DATA = original_data
            os.unlink(db_path)

    def test_correct_loss_settlement(self):
        """Verify P&L calculation for a losing bet."""
        # Bet: Home Win, but Away won. Expected Loss: -100
        bet = create_mock_bet_row(3, "Man United vs Liverpool", "Home", "1X2", 100.0, 1.8)
        db_path = self._create_temp_db([bet])
        
        mock_results = {
            "Man United vs Liverpool": (0, 1),  # Away wins
        }
        
        import agents.settler as settler_module
        
        try:
            original_data = settler_module.DATA
            settler_module.DATA = Path(db_path).parent
            
            with patch('free_results_scraper.get_finished_results', return_value=mock_results):
                result = self.agent.run({})
                
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT result, pnl FROM bet_log WHERE bet_id = 3").fetchone()
                conn.close()
                
                passed = (row[0] == "LOSS" and row[1] == -100.0)
                self.log("Correct Loss Calculation (1X2)", passed, f"PnL: {row[1]} (Expected -100.0)")
        finally:
            settler_module.DATA = original_data
            os.unlink(db_path)

    def test_over_under_push(self):
        """Bet: Over 2.0 Goals. Result: Exactly 2 goals. Should Void (Push)."""
        bet = create_mock_bet_row(4, "Team A vs Team B", "Over 2.0", "Over/Under", 100.0, 1.8)
        db_path = self._create_temp_db([bet])
        
        mock_results = {
            "Team A vs Team B": (1, 1),  # 2 goals total
        }
        
        import agents.settler as settler_module
        
        try:
            original_data = settler_module.DATA
            settler_module.DATA = Path(db_path).parent
            
            with patch('free_results_scraper.get_finished_results', return_value=mock_results):
                result = self.agent.run({})
                
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT result, pnl FROM bet_log WHERE bet_id = 4").fetchone()
                conn.close()
                
                passed = (row[0] == "VOID" and row[1] == 0.0)
                self.log("Over/Under Push (2 goals == 2.0)", passed, f"Status: {row[0]}, PnL: {row[1]}")
        finally:
            settler_module.DATA = original_data
            os.unlink(db_path)

    def test_btts_settlement(self):
        """Test BTTS settlement (Win and Loss cases)."""
        # BTTS Yes - Win
        bet1 = create_mock_bet_row(5, "A vs B", "Yes", "BTTS", 50.0, 1.7)
        # BTTS Yes - Loss (clean sheet)
        bet2 = create_mock_bet_row(6, "C vs D", "Yes", "BTTS", 50.0, 1.7)
        db_path = self._create_temp_db([bet1, bet2])
        
        mock_results = {
            "A vs B": (2, 1),  # Both scored
            "C vs D": (1, 0),  # Only one scored
        }
        
        import agents.settler as settler_module
        
        try:
            original_data = settler_module.DATA
            settler_module.DATA = Path(db_path).parent
            
            with patch('free_results_scraper.get_finished_results', return_value=mock_results):
                result = self.agent.run({})
                
                conn = sqlite3.connect(db_path)
                row1 = conn.execute("SELECT result, pnl FROM bet_log WHERE bet_id = 5").fetchone()
                row2 = conn.execute("SELECT result, pnl FROM bet_log WHERE bet_id = 6").fetchone()
                conn.close()
                
                passed = (row1[0] == "WIN" and row2[0] == "LOSS")
                self.log("BTTS Settlement (Win & Loss)", passed, f"Bet5: {row1[0]}, Bet6: {row2[0]}")
        finally:
            settler_module.DATA = original_data
            os.unlink(db_path)

    def test_team_name_normalization_integration(self):
        """Ensure 'Man United' matches 'Manchester United FC' in real settlement."""
        bet = create_mock_bet_row(7, "Man United vs Liverpool", "Home", "1X2", 100.0, 2.0)
        db_path = self._create_temp_db([bet])
        
        # API returns full official name
        mock_results = {
            "Manchester United FC vs Liverpool": (1, 0),
        }
        
        import agents.settler as settler_module
        
        try:
            original_data = settler_module.DATA
            settler_module.DATA = Path(db_path).parent
            
            with patch('free_results_scraper.get_finished_results', return_value=mock_results):
                result = self.agent.run({})
                
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT result, pnl FROM bet_log WHERE bet_id = 7").fetchone()
                conn.close()
                
                # Should settle because normalization matches
                passed = (row[0] == "WIN" and row[1] == 100.0)
                self.log("Team Name Normalization Integration", passed, f"Status: {row[0]}, PnL: {row[1]}")
        finally:
            settler_module.DATA = original_data
            os.unlink(db_path)

    def test_negative_score_rejection(self):
        """Ensure system doesn't settle on invalid negative scores."""
        bet = create_mock_bet_row(8, "A vs B", "Home", "1X2", 100.0, 2.0)
        db_path = self._create_temp_db([bet])
        
        # Bad data: Negative score (should be filtered out by settler)
        mock_results = {
            "A vs B": (-1, 2),
        }
        
        import agents.settler as settler_module
        
        try:
            original_data = settler_module.DATA
            settler_module.DATA = Path(db_path).parent
            
            with patch('free_results_scraper.get_finished_results', return_value=mock_results):
                result = self.agent.run({})
                
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT result FROM bet_log WHERE bet_id = 8").fetchone()
                conn.close()
                
                # Should NOT settle invalid data
                passed = row[0] is None
                self.log("Negative Score Validation", passed, f"Result: {row[0]} (should be NULL)")
        finally:
            settler_module.DATA = original_data
            os.unlink(db_path)

    def run_all(self):
        print("🚀 Starting Comprehensive Betting Settler Tests...\n")
        print("="*60)
        
        # Unit tests
        print("\n--- UNIT TESTS ---")
        self.test_normalize_team_name()
        self.test_match_teams_confidence()
        self.test_grade_1x2()
        self.test_grade_over_under()
        self.test_grade_btts()
        self.test_extract_line()
        
        # Integration tests
        print("\n--- INTEGRATION TESTS ---")
        self.test_early_settlement_prevention()
        self.test_correct_win_settlement()
        self.test_correct_loss_settlement()
        self.test_over_under_push()
        self.test_btts_settlement()
        self.test_team_name_normalization_integration()
        self.test_negative_score_rejection()

        print("\n" + "="*60)
        total = len(self.results)
        passed = sum(1 for r in self.results if r[1])
        failed = total - passed
        
        print(f"\n📊 TEST SUMMARY: {passed}/{total} Passed")
        if failed > 0:
            print(f"⚠️  {failed} tests FAILED. Review logic before deploying.")
            for name, result, details in self.results:
                if not result:
                    print(f"   ❌ {name}: {details}")
            return False
        else:
            print("🎉 All tests PASSED. Logic is sound and safe for deployment.")
            return True

if __name__ == "__main__":
    tester = TestScenarios()
    success = tester.run_all()
    sys.exit(0 if success else 1)
