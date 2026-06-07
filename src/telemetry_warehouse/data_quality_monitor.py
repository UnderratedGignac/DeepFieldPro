"""
data_quality_monitor.py
-----------------------
Monitors API health and data freshness.

Creates data_quality.db with tables:
- api_latency: Tracks timestamp of lineup releases vs kickoff
- odds_staleness: Tracks last time a market line ticked
"""

import os
import sys
import sqlite3
import datetime
from typing import Dict, List, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DataQualityMonitor:
    """
    Monitors data quality metrics:
    1. API Latency - Time between lineup release and kickoff
    2. Odds Staleness - Time since last odds update
    3. Missing Lineups - Fixtures without confirmed lineups near kickoff
    """
    
    def __init__(self, db_path: str = "data/data_quality.db"):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(self.base_dir, db_path)
        
        self._init_database()
    
    def _init_database(self):
        """Initialize data_quality.db with required tables."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # Table 1: API Latency - tracks lineup release timing
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_latency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id TEXT,
                    match_name TEXT,
                    league TEXT,
                    kickoff_time TEXT,
                    lineup_detected_time TEXT,
                    minutes_before_kickoff REAL,
                    api_source TEXT,
                    recorded_at TEXT
                )
            """)
            
            # Table 2: Odds Staleness - tracks market line ticks
            cur.execute("""
                CREATE TABLE IF NOT EXISTS odds_staleness (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT,
                    player_name TEXT,
                    team TEXT,
                    market_type TEXT,
                    selection TEXT,
                    last_tick_time TEXT,
                    odds_value REAL,
                    bookmaker TEXT,
                    staleness_minutes REAL,
                    recorded_at TEXT
                )
            """)
            
            # Table 3: Missing Lineups - tracks fixtures without lineups
            cur.execute("""
                CREATE TABLE IF NOT EXISTS missing_lineups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id TEXT,
                    match_name TEXT,
                    league TEXT,
                    kickoff_time TEXT,
                    minutes_to_kickoff REAL,
                    status TEXT,
                    checked_at TEXT
                )
            """)
            
            # Table 4: API Health Summary - aggregated metrics
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_health_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    api_source TEXT,
                    avg_latency_minutes REAL,
                    max_latency_minutes REAL,
                    total_checks INTEGER,
                    failed_checks INTEGER,
                    health_score REAL,
                    recorded_at TEXT
                )
            """)
            
            # Create indexes for faster queries
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fixture ON api_latency(fixture_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_market ON odds_staleness(market_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_last_tick ON odds_staleness(last_tick_time)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kickoff ON missing_lineups(kickoff_time)")
            
            conn.commit()
            conn.close()
            
            print(f"[DataQualityMonitor] Database initialized at {self.db_path}")
        except Exception as e:
            print(f"[DataQualityMonitor] Error initializing database: {e}")
    
    def record_lineup_latency(self, fixture_id: str, match_name: str, league: str,
                             kickoff_time: datetime.datetime, 
                             lineup_detected_time: datetime.datetime,
                             api_source: str = "api-football"):
        """
        Record when lineups were detected relative to kickoff.
        
        Args:
            fixture_id: Unique fixture identifier
            match_name: Match description (e.g., "Home vs Away")
            league: League name
            kickoff_time: Scheduled kickoff time
            lineup_detected_time: When lineups were first detected
            api_source: API provider name
        """
        try:
            # Calculate minutes before kickoff
            if kickoff_time.tzinfo is None:
                kickoff_time = kickoff_time.replace(tzinfo=datetime.timezone.utc)
            if lineup_detected_time.tzinfo is None:
                lineup_detected_time = lineup_detected_time.replace(tzinfo=datetime.timezone.utc)
            
            minutes_before = (kickoff_time - lineup_detected_time).total_seconds() / 60.0
            
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO api_latency (
                    fixture_id, match_name, league, kickoff_time,
                    lineup_detected_time, minutes_before_kickoff,
                    api_source, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(fixture_id),
                match_name,
                league,
                kickoff_time.isoformat(),
                lineup_detected_time.isoformat(),
                minutes_before,
                api_source,
                datetime.datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            print(f"[DataQualityMonitor] Lineup latency recorded: {minutes_before:.1f} mins before kickoff")
        except Exception as e:
            print(f"[DataQualityMonitor] Error recording lineup latency: {e}")
    
    def record_odds_tick(self, market_id: str, player_name: str, team: str,
                        market_type: str, selection: str, odds_value: float,
                        bookmaker: str = "betarabia"):
        """
        Record an odds update (tick) for a market.
        
        Args:
            market_id: Unique market identifier
            player_name: Player name (for prop markets)
            team: Team name
            market_type: Market type (e.g., "shots", "sot", "passes")
            selection: Bet selection (e.g., "Over 2.5")
            odds_value: Decimal odds value
            bookmaker: Bookmaker name
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        
        try:
            # Calculate staleness from previous tick
            staleness_minutes = self._get_market_staleness(market_id)
            
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # Update existing record or insert new
            cur.execute("""
                INSERT INTO odds_staleness (
                    market_id, player_name, team, market_type, selection,
                    last_tick_time, odds_value, bookmaker, staleness_minutes, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                market_id,
                player_name,
                team,
                market_type,
                selection,
                now.isoformat(),
                odds_value,
                bookmaker,
                staleness_minutes,
                now.isoformat()
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DataQualityMonitor] Error recording odds tick: {e}")
    
    def _get_market_staleness(self, market_id: str) -> float:
        """Get minutes since last tick for a market."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            cur.execute("""
                SELECT last_tick_time FROM odds_staleness
                WHERE market_id = ?
                ORDER BY id DESC LIMIT 1
            """, (market_id,))
            
            row = cur.fetchone()
            conn.close()
            
            if row and row[0]:
                last_tick = datetime.datetime.fromisoformat(row[0])
                if last_tick.tzinfo is None:
                    last_tick = last_tick.replace(tzinfo=datetime.timezone.utc)
                
                now = datetime.datetime.now(datetime.timezone.utc)
                return (now - last_tick).total_seconds() / 60.0
            
            return 0.0  # First tick
        except Exception:
            return 0.0
    
    def record_missing_lineup(self, fixture_id: str, match_name: str, league: str,
                             kickoff_time: datetime.datetime, minutes_to_kickoff: float,
                             status: str = "missing"):
        """
        Record a fixture that is missing lineups near kickoff.
        
        Args:
            fixture_id: Unique fixture identifier
            match_name: Match description
            league: League name
            kickoff_time: Scheduled kickoff time
            minutes_to_kickoff: Minutes until kickoff
            status: Status ("missing", "delayed", "confirmed")
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO missing_lineups (
                    fixture_id, match_name, league, kickoff_time,
                    minutes_to_kickoff, status, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(fixture_id),
                match_name,
                league,
                kickoff_time.isoformat() if isinstance(kickoff_time, datetime.datetime) else kickoff_time,
                minutes_to_kickoff,
                status,
                datetime.datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DataQualityMonitor] Error recording missing lineup: {e}")
    
    def get_stale_markets(self, threshold_minutes: float = 15.0) -> List[Dict]:
        """
        Get all markets with stale odds (no tick in threshold_minutes).
        
        Args:
            threshold_minutes: Minimum minutes without update to be considered stale
            
        Returns:
            List of stale market records
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - 
                     datetime.timedelta(minutes=threshold_minutes)).isoformat()
            
            cur.execute("""
                SELECT DISTINCT market_id, player_name, team, market_type,
                       selection, last_tick_time, odds_value, bookmaker
                FROM odds_staleness
                WHERE last_tick_time < ?
                AND market_id IN (
                    SELECT market_id FROM odds_staleness
                    GROUP BY market_id
                    HAVING MAX(id) = id
                )
                ORDER BY last_tick_time ASC
            """, (cutoff,))
            
            results = [dict(row) for row in cur.fetchall()]
            conn.close()
            
            return results
        except Exception as e:
            print(f"[DataQualityMonitor] Error getting stale markets: {e}")
            return []
    
    def get_api_health_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Get API health summary for the past N days.
        
        Args:
            days: Number of days to summarize
            
        Returns:
            Dict with health metrics
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).date().isoformat()
            
            # Get latency stats
            cur.execute("""
                SELECT 
                    api_source,
                    AVG(minutes_before_kickoff) as avg_latency,
                    MAX(minutes_before_kickoff) as max_latency,
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN minutes_before_kickoff < 30 THEN 1 ELSE 0 END) as late_releases
                FROM api_latency
                WHERE date(recorded_at) >= ?
                GROUP BY api_source
            """, (cutoff_date,))
            
            latency_stats = [dict(row) for row in cur.fetchall()]
            
            # Get odds freshness stats
            cur.execute("""
                SELECT 
                    AVG(staleness_minutes) as avg_staleness,
                    MAX(staleness_minutes) as max_staleness,
                    COUNT(*) as total_ticks
                FROM odds_staleness
                WHERE date(recorded_at) >= ?
            """, (cutoff_date,))
            
            freshness_stats = dict(cur.fetchone())
            conn.close()
            
            # Calculate overall health score (0-100)
            total_checks = sum(s.get('total_checks', 0) for s in latency_stats)
            late_releases = sum(s.get('late_releases', 0) for s in latency_stats)
            
            if total_checks > 0:
                on_time_pct = ((total_checks - late_releases) / total_checks) * 100
            else:
                on_time_pct = 100
            
            health_score = max(0, min(100, on_time_pct))
            
            return {
                'period_days': days,
                'health_score': health_score,
                'lineup_stats': {
                    'total_checks': total_checks,
                    'late_releases': late_releases,
                    'on_time_pct': on_time_pct,
                    'by_source': latency_stats
                },
                'odds_freshness': {
                    'avg_staleness_minutes': freshness_stats.get('avg_staleness', 0),
                    'max_staleness_minutes': freshness_stats.get('max_staleness', 0),
                    'total_ticks': freshness_stats.get('total_ticks', 0)
                }
            }
        
        except Exception as e:
            print(f"[DataQualityMonitor] Error getting health summary: {e}")
            return {
                'period_days': days,
                'health_score': 0,
                'lineup_stats': {},
                'odds_freshness': {}
            }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get real-time data for the Data Quality dashboard tab.
        
        Returns:
            Dict with current status for UI display
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Get stale markets
        stale_markets = self.get_stale_markets(threshold_minutes=15.0)
        
        # Get recent missing lineups (within 2 hours)
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            two_hours_ago = (now - datetime.timedelta(hours=2)).isoformat()
            
            cur.execute("""
                SELECT fixture_id, match_name, league, kickoff_time, 
                       minutes_to_kickoff, status
                FROM missing_lineups
                WHERE checked_at > ?
                ORDER BY minutes_to_kickoff ASC
                LIMIT 20
            """, (two_hours_ago,))
            
            missing_lineups = [dict(row) for row in cur.fetchall()]
            conn.close()
        except Exception:
            missing_lineups = []
        
        # Get health summary
        health_summary = self.get_api_health_summary(days=7)
        
        return {
            'timestamp': now.isoformat(),
            'stale_markets_count': len(stale_markets),
            'stale_markets': stale_markets[:10],  # Top 10
            'missing_lineups_count': len(missing_lineups),
            'missing_lineups': missing_lineups,
            'health_score': health_summary.get('health_score', 0),
            'health_summary': health_summary
        }


def create_data_quality_monitor(db_path: str = "data/data_quality.db") -> DataQualityMonitor:
    """Factory function to create configured DataQualityMonitor instance."""
    return DataQualityMonitor(db_path=db_path)


if __name__ == "__main__":
    print("Data Quality Monitor Module Loaded.")
    print("Usage: Track API latency and odds staleness for system health monitoring.")
    
    # Example usage
    monitor = create_data_quality_monitor()
    
    # Record a lineup latency event
    kickoff = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    lineup_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=35)
    
    monitor.record_lineup_latency(
        fixture_id="test_123",
        match_name="Man City vs Liverpool",
        league="Premier League",
        kickoff_time=kickoff,
        lineup_detected_time=lineup_time,
        api_source="api-football"
    )
    
    # Record an odds tick
    monitor.record_odds_tick(
        market_id="shots_haaland_2.5",
        player_name="Erling Haaland",
        team="Manchester City",
        market_type="shots",
        selection="Over 2.5",
        odds_value=2.10,
        bookmaker="betarabia"
    )
    
    # Get dashboard data
    dashboard = monitor.get_dashboard_data()
    print("\nDashboard Data:")
    print(f"  Health Score: {dashboard['health_score']:.1f}")
    print(f"  Stale Markets: {dashboard['stale_markets_count']}")
    print(f"  Missing Lineups: {dashboard['missing_lineups_count']}")
