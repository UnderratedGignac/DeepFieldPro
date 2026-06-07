"""
no_bet_filter.py
----------------
The Gatekeeper: Rejects bets even if EV is technically positive.

Rules:
- reject_if_uncertainty_high(): Blocks bet if P90 - P10 xMin spread > 30 mins
- reject_if_stale_odds(): Blocks bet if odds haven't changed in 15+ minutes
- reject_if_correlated(): Blocks bet if we have exposure to same team/player
"""

import datetime
from typing import Dict, List, Optional, Any
import sqlite3
import os


class NoBetFilter:
    """
    Risk management gatekeeper that vetoes bets based on:
    1. High uncertainty in player minutes
    2. Stale odds (no market movement)
    3. Correlated exposure (concentration risk)
    """
    
    MAX_UNCERTAINTY_SPREAD = 30  # Minutes (P90 - P10 threshold)
    ODDS_STALENESS_THRESHOLD = 15  # Minutes without tick
    MAX_TEAM_EXPOSURE = 3  # Max bets on same team
    MAX_PLAYER_EXPOSURE = 1  # Max bets per player
    
    def __init__(self, db_path: str = "data/bet_log.db"):
        self.db_path = db_path
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(self.base_dir, db_path)
        
        # In-memory cache of active exposures
        self.active_exposures: Dict[str, List[Dict]] = {
            'teams': {},
            'players': {}
        }
        
        self._load_active_exposures()
    
    def _load_active_exposures(self):
        """Load current active bets from database."""
        if not os.path.exists(self.db_path):
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # Check if bets table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bets'")
            if not cur.fetchone():
                conn.close()
                return
            
            # Load unsettled bets
            cur.execute("""
                SELECT player_name, team, market, stake, status 
                FROM bets 
                WHERE status IN ('open', 'pending', 'active')
            """)
            
            for row in cur.fetchall():
                player, team, market, stake, status = row
                
                # Track team exposure
                if team:
                    if team not in self.active_exposures['teams']:
                        self.active_exposures['teams'][team] = []
                    self.active_exposures['teams'][team].append({
                        'player': player,
                        'market': market,
                        'stake': stake
                    })
                
                # Track player exposure
                if player:
                    if player not in self.active_exposures['players']:
                        self.active_exposures['players'][player] = []
                    self.active_exposures['players'][player].append({
                        'team': team,
                        'market': market,
                        'stake': stake
                    })
            
            conn.close()
        except Exception as e:
            print(f"[NoBetFilter] Error loading exposures: {e}")
    
    def reject_if_uncertainty_high(self, xmin_p10: float, xmin_p90: float) -> tuple:
        """
        Block bet if P90 - P10 xMin spread > 30 minutes.
        
        Args:
            xmin_p10: P10 expected minutes
            xmin_p90: P90 expected minutes
            
        Returns:
            Tuple of (rejected: bool, reason: str or None)
        """
        spread = xmin_p90 - xmin_p10
        
        if spread > self.MAX_UNCERTAINTY_SPREAD:
            return True, f"High uncertainty: P90-P10 spread = {spread:.1f} mins (max: {self.MAX_UNCERTAINTY_SPREAD})"
        
        return False, None
    
    def reject_if_stale_odds(self, last_tick_timestamp: Optional[datetime.datetime],
                            current_time: Optional[datetime.datetime] = None) -> tuple:
        """
        Block bet if odds haven't changed in 15+ minutes.
        
        Args:
            last_tick_timestamp: When the odds last updated
            current_time: Current timestamp (defaults to now)
            
        Returns:
            Tuple of (rejected: bool, reason: str or None)
        """
        if last_tick_timestamp is None:
            return True, "No odds timestamp available - market may be stale"
        
        if current_time is None:
            current_time = datetime.datetime.now(datetime.timezone.utc)
        
        # Ensure timezone awareness
        if last_tick_timestamp.tzinfo is None:
            last_tick_timestamp = last_tick_timestamp.replace(tzinfo=datetime.timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=datetime.timezone.utc)
        
        minutes_since_tick = (current_time - last_tick_timestamp).total_seconds() / 60.0
        
        if minutes_since_tick > self.ODDS_STALENESS_THRESHOLD:
            return True, f"Stale odds: Last tick {minutes_since_tick:.1f} mins ago (max: {self.ODDS_STALENESS_THRESHOLD})"
        
        return False, None
    
    def reject_if_correlated(self, team: str, player: str, 
                            market: str) -> tuple:
        """
        Block bet if we already have exposure to the same team/player.
        
        Args:
            team: Team name
            player: Player name
            market: Market type (e.g., "shots_over", "sot_under")
            
        Returns:
            Tuple of (rejected: bool, reason: str or None)
        """
        reasons = []
        
        # Check team exposure
        if team in self.active_exposures['teams']:
            team_bets = self.active_exposures['teams'][team]
            if len(team_bets) >= self.MAX_TEAM_EXPOSURE:
                reasons.append(f"Max team exposure ({self.MAX_TEAM_EXPOSURE} bets on {team})")
        
        # Check player exposure  
        if player in self.active_exposures['players']:
            player_bets = self.active_exposures['players'][player]
            if len(player_bets) >= self.MAX_PLAYER_EXPOSURE:
                reasons.append(f"Max player exposure ({self.MAX_PLAYER_EXPOSURE} bets on {player})")
        
        # Check for same market on same team (correlation risk)
        if team in self.active_exposures['teams']:
            same_market_count = sum(
                1 for bet in self.active_exposures['teams'][team]
                if market.split('_')[0] == bet['market'].split('_')[0]
            )
            if same_market_count >= 2:
                reasons.append(f"Correlated exposure: {same_market_count} similar markets on {team}")
        
        if reasons:
            return True, "; ".join(reasons)
        
        return False, None
    
    def evaluate_bet(self, bet_proposal: Dict[str, Any]) -> tuple:
        """
        Run all filters on a bet proposal.
        
        Args:
            bet_proposal: Dict containing:
                - player_name: str
                - team: str
                - market: str
                - xmin_p10: float
                - xmin_p90: float
                - odds_last_tick: datetime
                - stake: float
                
        Returns:
            Tuple of (approved: bool, rejection_reason: str or None)
        """
        player = bet_proposal.get('player_name', '')
        team = bet_proposal.get('team', '')
        market = bet_proposal.get('market', '')
        xmin_p10 = bet_proposal.get('xmin_p10', 0)
        xmin_p90 = bet_proposal.get('xmin_p90', 100)
        odds_tick = bet_proposal.get('odds_last_tick')
        
        # Filter 1: Uncertainty check
        rejected, reason = self.reject_if_uncertainty_high(xmin_p10, xmin_p90)
        if rejected:
            return False, reason
        
        # Filter 2: Stale odds check
        rejected, reason = self.reject_if_stale_odds(odds_tick)
        if rejected:
            return False, reason
        
        # Filter 3: Correlation check
        rejected, reason = self.reject_if_correlated(team, player, market)
        if rejected:
            return False, reason
        
        return True, None
    
    def record_bet(self, player: str, team: str, market: str, stake: float):
        """Record a placed bet for future correlation checks."""
        if team not in self.active_exposures['teams']:
            self.active_exposures['teams'][team] = []
        self.active_exposures['teams'][team].append({
            'player': player,
            'market': market,
            'stake': stake
        })
        
        if player not in self.active_exposures['players']:
            self.active_exposures['players'][player] = []
        self.active_exposures['players'][player].append({
            'team': team,
            'market': market,
            'stake': stake
        })
    
    def clear_settled_exposures(self, settled_bet_ids: List[str]):
        """Remove settled bets from exposure tracking."""
        # In production, this would query the database and update exposures
        # For now, just reload from DB
        self._load_active_exposures()


def create_no_bet_filter(db_path: str = "data/bet_log.db") -> NoBetFilter:
    """Factory function to create configured NoBetFilter instance."""
    return NoBetFilter(db_path=db_path)


if __name__ == "__main__":
    print("No-Bet Filter Module Loaded.")
    print("Usage: Pass bet proposals through NoBetFilter.evaluate_bet() before placing.")
    
    # Example usage
    filter_instance = create_no_bet_filter()
    
    test_bet = {
        'player_name': 'Erling Haaland',
        'team': 'Manchester City',
        'market': 'shots_over_2.5',
        'xmin_p10': 60,
        'xmin_p90': 85,
        'odds_last_tick': datetime.datetime.now(datetime.timezone.utc),
        'stake': 100
    }
    
    approved, reason = filter_instance.evaluate_bet(test_bet)
    print("\\nTest Bet Evaluation:")
    print(f"  Approved: {approved}")
    print(f"  Reason: {reason or 'All checks passed'}")
