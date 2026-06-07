"""
clv_tracker.py
--------------
The CLV Scraper: Ultimate source of truth for model performance.

Runs a background async thread that wakes up 60 seconds before a match starts,
queries Betarabia/Pinnacle for final odds, and writes them to bet_log.db.

Tracks Closing Line Value (CLV) = (closing_odds / bet_odds) - 1
"""

import os
import sys
import time
import threading
import datetime
import sqlite3
from typing import Dict, Optional, Any
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CLVTracker:
    """
    Tracks Closing Line Value for all placed bets.
    
    CLV measures whether we got better odds than the closing line,
    which is the most accurate measure of bet quality.
    """
    
    def __init__(self, db_path: str = "data/bet_log.db"):
        self.db_path = db_path
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(self.base_dir, db_path)
        
        # Scheduled CLV captures
        self.scheduled_captures: Dict[str, Dict] = {}
        
        self._init_database()
    
    def _init_database(self):
        """Initialize bet_log.db with CLV columns if they don't exist."""
        if not os.path.exists(self.db_path):
            # Create the database file
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.close()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # Create bets table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    bet_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    player_name TEXT,
                    team TEXT,
                    market TEXT,
                    selection TEXT,
                    entry_odds REAL,
                    stake REAL,
                    fair_prob REAL,
                    status TEXT DEFAULT 'open',
                    outcome TEXT,
                    profit_loss REAL,
                    closing_odds REAL,
                    clv_percentage REAL,
                    uncertainty_spread REAL,
                    kickoff_time TEXT
                )
            """)
            
            # Check if CLV columns exist and add them if not
            cur.execute("PRAGMA table_info(bets)")
            columns = {col[1]: col[2] for col in cur.fetchall()}
            
            if 'closing_odds' not in columns:
                cur.execute("ALTER TABLE bets ADD COLUMN closing_odds REAL")
            if 'clv_percentage' not in columns:
                cur.execute("ALTER TABLE bets ADD COLUMN clv_percentage REAL")
            if 'uncertainty_spread' not in columns:
                cur.execute("ALTER TABLE bets ADD COLUMN uncertainty_spread REAL")
            if 'kickoff_time' not in columns:
                cur.execute("ALTER TABLE bets ADD COLUMN kickoff_time TEXT")
            
            # Create predictions table for tracking pre-match data
            cur.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    fixture_id TEXT PRIMARY KEY,
                    match_name TEXT,
                    league TEXT,
                    kickoff TEXT,
                    prediction TEXT,
                    expected_score TEXT,
                    home_prob REAL,
                    draw_prob REAL,
                    away_prob REAL,
                    over_prob REAL,
                    under_prob REAL,
                    btts_yes_prob REAL,
                    btts_no_prob REAL,
                    has_lineup INTEGER,
                    predicted_at TIMESTAMP,
                    extra_json TEXT
                )
            """)
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CLVTracker] Error initializing database: {e}")
    
    def schedule_clv_capture(self, bet_id: str, kickoff_time: datetime.datetime,
                            entry_odds: float, player_name: str, team: str,
                            market: str, uncertainty_spread: float = 0):
        """
        Schedule a CLV capture to run 60 seconds before kickoff.
        
        Args:
            bet_id: Unique bet identifier
            kickoff_time: Match kickoff time
            entry_odds: Odds at bet placement
            player_name: Player name
            team: Team name
            market: Market type
            uncertainty_spread: P90 - P10 minutes spread
        """
        # Schedule for 60 seconds before kickoff
        capture_time = kickoff_time - datetime.timedelta(seconds=60)
        
        self.scheduled_captures[bet_id] = {
            'bet_id': bet_id,
            'kickoff_time': kickoff_time,
            'capture_time': capture_time,
            'entry_odds': entry_odds,
            'player_name': player_name,
            'team': team,
            'market': market,
            'uncertainty_spread': uncertainty_spread,
            'status': 'scheduled'
        }
        
        # Start background thread to monitor and capture
        thread = threading.Thread(target=self._monitor_and_capture, args=(bet_id,), daemon=True)
        thread.start()
        
        print(f"[CLVTracker] Scheduled CLV capture for bet {bet_id} at {capture_time.strftime('%H:%M:%S')}")
    
    def _monitor_and_capture(self, bet_id: str):
        """Background thread to monitor time and capture closing odds."""
        if bet_id not in self.scheduled_captures:
            return
        
        capture_info = self.scheduled_captures[bet_id]
        capture_time = capture_info['capture_time']
        
        while True:
            now = datetime.datetime.now(datetime.timezone.utc)
            
            # Ensure timezone awareness
            if capture_time.tzinfo is None:
                capture_time = capture_time.replace(tzinfo=datetime.timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=datetime.timezone.utc)
            
            if now >= capture_time:
                self._capture_closing_odds(bet_id)
                break
            
            time.sleep(10)  # Check every 10 seconds
    
    def _capture_closing_odds(self, bet_id: str):
        """
        Capture closing odds from the market.
        
        In production, this would query Betarabia/Pinnacle APIs.
        For now, we simulate by querying our odds database.
        """
        if bet_id not in self.scheduled_captures:
            return
        
        capture_info = self.scheduled_captures[bet_id]
        player_name = capture_info['player_name']
        team = capture_info['team']
        market = capture_info['market']
        entry_odds = capture_info['entry_odds']
        uncertainty_spread = capture_info['uncertainty_spread']
        
        print(f"[CLVTracker] Capturing closing odds for bet {bet_id} ({player_name} - {market})")
        
        # Try to get closing odds from odds database
        closing_odds = self._fetch_closing_odds(player_name, team, market)
        
        if closing_odds is None:
            # Fallback: use entry odds if no closing line available
            closing_odds = entry_odds
            print(f"[CLVTracker] No closing odds found, using entry odds: {closing_odds}")
        
        # Calculate CLV percentage: (closing_odds / entry_odds) - 1
        clv_percentage = (closing_odds / entry_odds) - 1
        
        # Update database
        self._update_bet_with_clv(bet_id, closing_odds, clv_percentage, uncertainty_spread)
        
        # Mark as captured
        capture_info['status'] = 'captured'
        capture_info['closing_odds'] = closing_odds
        capture_info['clv_percentage'] = clv_percentage
        
        print(f"[CLVTracker] CLV recorded for {bet_id}: {clv_percentage*100:.2f}% (entry: {entry_odds}, close: {closing_odds})")
    
    def _fetch_closing_odds(self, player_name: str, team: str, market: str) -> Optional[float]:
        """
        Fetch closing odds from odds database or external API.
        
        Returns:
            Decimal odds or None if not available
        """
        # Try to fetch from odds_stream.db
        odds_db = os.path.join(self.base_dir, "data", "odds_stream.db")
        
        if os.path.exists(odds_db):
            try:
                conn = sqlite3.connect(odds_db)
                cur = conn.cursor()
                
                # Query latest odds for this market
                cur.execute("""
                    SELECT decimal_odds FROM odds 
                    WHERE player_name = ? AND market = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (player_name, market))
                
                row = cur.fetchone()
                conn.close()
                
                if row:
                    return float(row[0])
            except Exception as e:
                print(f"[CLVTracker] Error fetching odds from DB: {e}")
        
        # Fallback: Try betarabia scraper cache
        betarabia_cache = os.path.join(self.base_dir, "data", "betarabia_cache.json")
        if os.path.exists(betarabia_cache):
            try:
                with open(betarabia_cache, 'r') as f:
                    cache = json.load(f)
                
                # Search for matching market
                for market_data in cache.get('markets', []):
                    if player_name.lower() in market_data.get('selection', '').lower():
                        if market.split('_')[0] in market_data.get('market_type', '').lower():
                            return float(market_data.get('odds', 0))
            except Exception:
                pass
        
        return None
    
    def _update_bet_with_clv(self, bet_id: str, closing_odds: float,
                            clv_percentage: float, uncertainty_spread: float):
        """Update bet record with CLV data."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # Check if bets table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bets'")
            if not cur.fetchone():
                conn.close()
                return
            
            cur.execute("""
                UPDATE bets 
                SET closing_odds = ?, 
                    clv_percentage = ?,
                    uncertainty_spread = ?
                WHERE bet_id = ?
            """, (closing_odds, clv_percentage, uncertainty_spread, bet_id))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CLVTracker] Error updating bet with CLV: {e}")
    
    def record_bet_for_clv(self, bet_data: Dict[str, Any]):
        """
        Record a new bet and schedule CLV tracking.
        
        Args:
            bet_data: Dict containing:
                - bet_id: str
                - player_name: str
                - team: str
                - market: str
                - entry_odds: float
                - kickoff_time: datetime
                - xmin_p10: float (optional)
                - xmin_p90: float (optional)
        """
        bet_id = bet_data.get('bet_id')
        kickoff_time = bet_data.get('kickoff_time')
        
        if not bet_id or not kickoff_time:
            print("[CLVTracker] Missing bet_id or kickoff_time, skipping CLV scheduling")
            return
        
        # Calculate uncertainty spread if xMin data provided
        uncertainty_spread = 0
        if 'xmin_p10' in bet_data and 'xmin_p90' in bet_data:
            uncertainty_spread = bet_data['xmin_p90'] - bet_data['xmin_p10']
        
        # Save bet to database
        self._save_bet_to_db(bet_data, uncertainty_spread)
        
        # Schedule CLV capture
        self.schedule_clv_capture(
            bet_id=bet_id,
            kickoff_time=kickoff_time,
            entry_odds=bet_data.get('entry_odds', 1.0),
            player_name=bet_data.get('player_name', ''),
            team=bet_data.get('team', ''),
            market=bet_data.get('market', ''),
            uncertainty_spread=uncertainty_spread
        )
    
    def _save_bet_to_db(self, bet_data: Dict[str, Any], uncertainty_spread: float):
        """Save bet record to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            kickoff_str = bet_data.get('kickoff_time')
            if isinstance(kickoff_str, datetime.datetime):
                kickoff_str = kickoff_str.isoformat()
            
            cur.execute("""
                INSERT OR REPLACE INTO bets (
                    bet_id, timestamp, player_name, team, market, selection,
                    entry_odds, stake, fair_prob, status, kickoff_time, uncertainty_spread
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bet_data.get('bet_id'),
                datetime.datetime.now().isoformat(),
                bet_data.get('player_name'),
                bet_data.get('team'),
                bet_data.get('market'),
                bet_data.get('selection', ''),
                bet_data.get('entry_odds'),
                bet_data.get('stake', 0),
                bet_data.get('fair_prob', 0),
                'open',
                kickoff_str,
                uncertainty_spread
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CLVTracker] Error saving bet to DB: {e}")
    
    def get_clv_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Get CLV performance summary.
        
        Args:
            days: Number of days to summarize
            
        Returns:
            Dict with avg_clv, positive_clv_pct, total_bets
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
            
            cur.execute("""
                SELECT 
                    AVG(clv_percentage) as avg_clv,
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN clv_percentage > 0 THEN 1 ELSE 0 END) as positive_clv
                FROM bets
                WHERE timestamp > ? AND clv_percentage IS NOT NULL
            """, (cutoff_date,))
            
            row = cur.fetchone()
            conn.close()
            
            if row and row[1] > 0:
                total = row[1]
                positive = row[2] or 0
                return {
                    'avg_clv': row[0] or 0,
                    'avg_clv_pct': (row[0] or 0) * 100,
                    'positive_clv_count': positive,
                    'positive_clv_pct': (positive / total) * 100,
                    'total_bets': total
                }
            
            return {'avg_clv': 0, 'avg_clv_pct': 0, 'positive_clv_count': 0, 
                   'positive_clv_pct': 0, 'total_bets': 0}
        
        except Exception as e:
            print(f"[CLVTracker] Error getting CLV summary: {e}")
            return {'avg_clv': 0, 'avg_clv_pct': 0, 'positive_clv_count': 0,
                   'positive_clv_pct': 0, 'total_bets': 0}


def create_clv_tracker(db_path: str = "data/bet_log.db") -> CLVTracker:
    """Factory function to create configured CLVTracker instance."""
    return CLVTracker(db_path=db_path)


if __name__ == "__main__":
    print("CLV Tracker Module Loaded.")
    print("Usage: Call record_bet_for_clv() when placing a bet to auto-track CLV.")
    
    # Example usage
    tracker = create_clv_tracker()
    
    test_bet = {
        'bet_id': 'test_001',
        'player_name': 'Erling Haaland',
        'team': 'Manchester City',
        'market': 'shots_over_2.5',
        'selection': 'Over 2.5 Shots',
        'entry_odds': 2.10,
        'stake': 100,
        'fair_prob': 0.52,
        'kickoff_time': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2),
        'xmin_p10': 65,
        'xmin_p90': 85
    }
    
    tracker.record_bet_for_clv(test_bet)
    print("\nCLV capture scheduled. Will execute 60 seconds before kickoff.")
