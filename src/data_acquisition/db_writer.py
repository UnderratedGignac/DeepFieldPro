import sqlite3
import asyncio
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

DB_PATH = "C:/Users/Elie/DeepFieldPro/src/live_data.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # parsed_lineups table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS parsed_lineups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id TEXT,
            player_name TEXT,
            normalized_name TEXT,
            team TEXT,
            starter BOOLEAN,
            position TEXT,
            formation TEXT,
            source TEXT,
            confidence_score REAL,
            scraped_at TEXT,
            UNIQUE(fixture_id, normalized_name)
        )
    """
    )

    # lineup_history table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lineup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id TEXT,
            source TEXT,
            lineup_payload TEXT,
            lineup_version INTEGER,
            timestamp TEXT
        )
    """
    )

    # odds_stream table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS odds_stream (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id TEXT,
            bookmaker TEXT,
            market TEXT,
            player_name TEXT,
            normalized_name TEXT,
            line REAL,
            side TEXT,
            decimal_odds REAL,
            implied_probability REAL,
            market_status TEXT,
            scraped_at TEXT,
            UNIQUE(fixture_id, bookmaker, market, normalized_name, line, side)
        )
    """
    )

    # odds_history table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS odds_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id TEXT,
            market TEXT,
            player_name TEXT,
            old_odds REAL,
            new_odds REAL,
            movement REAL,
            timestamp TEXT
        )
    """
    )

    conn.commit()
    conn.close()


class DBWriter:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        init_db()

    def _insert_lineups_sync(
        self, fixture_id: str, source: str, lineups: List[Dict[str, Any]]
    ):
        import json
        from datetime import datetime, timezone

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. Versioning: Store Snapshot
        cursor.execute(
            "SELECT MAX(lineup_version) FROM lineup_history WHERE fixture_id=?",
            (fixture_id,),
        )
        row = cursor.fetchone()
        version = (row[0] or 0) + 1

        timestamp = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(lineups)

        cursor.execute(
            """
            INSERT INTO lineup_history (fixture_id, source, lineup_payload, lineup_version, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """,
            (fixture_id, source, payload_str, version, timestamp),
        )

        # 2. Update live state
        for player in lineups:
            cursor.execute(
                """
                INSERT OR REPLACE INTO parsed_lineups 
                (fixture_id, player_name, normalized_name, team, starter, position, formation, source, confidence_score, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    player.get("fixture_id"),
                    player.get("player_name"),
                    player.get("normalized_name"),
                    player.get("team"),
                    player.get("starter"),
                    player.get("position"),
                    player.get("formation"),
                    player.get("source"),
                    player.get("confidence_score"),
                    player.get("scraped_at"),
                ),
            )
        conn.commit()
        conn.close()

    def _insert_odds_sync(self, odds: List[Dict[str, Any]]):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for odd in odds:
            # First, check if odds exist and get old odds to track history
            cursor.execute(
                """
                SELECT decimal_odds FROM odds_stream
                WHERE fixture_id=? AND bookmaker=? AND market=? AND normalized_name=? AND line=? AND side=?
            """,
                (
                    odd.get("fixture_id"),
                    odd.get("bookmaker"),
                    odd.get("market"),
                    odd.get("normalized_name"),
                    odd.get("line"),
                    odd.get("side"),
                ),
            )

            row = cursor.fetchone()

            if row:
                old_odds = row[0]
                new_odds = odd.get("decimal_odds")
                if old_odds != new_odds:
                    movement = new_odds - old_odds
                    # Log history
                    cursor.execute(
                        """
                        INSERT INTO odds_history (fixture_id, market, player_name, old_odds, new_odds, movement, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            odd.get("fixture_id"),
                            odd.get("market"),
                            odd.get("player_name"),
                            old_odds,
                            new_odds,
                            movement,
                            odd.get("scraped_at"),
                        ),
                    )

            # Insert or replace live stream
            cursor.execute(
                """
                INSERT OR REPLACE INTO odds_stream 
                (fixture_id, bookmaker, market, player_name, normalized_name, line, side, decimal_odds, implied_probability, market_status, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    odd.get("fixture_id"),
                    odd.get("bookmaker"),
                    odd.get("market"),
                    odd.get("player_name"),
                    odd.get("normalized_name"),
                    odd.get("line"),
                    odd.get("side"),
                    odd.get("decimal_odds"),
                    odd.get("implied_probability"),
                    odd.get("market_status"),
                    odd.get("scraped_at"),
                ),
            )
        conn.commit()
        conn.close()

    async def insert_lineups(
        self, fixture_id: str, source: str, lineups: List[Dict[str, Any]]
    ):
        await asyncio.to_thread(self._insert_lineups_sync, fixture_id, source, lineups)
        logger.info(
            f"Inserted/Updated {len(lineups)} lineup records for {fixture_id} (Source: {source})."
        )

    async def insert_odds(self, odds: List[Dict[str, Any]]):
        await asyncio.to_thread(self._insert_odds_sync, odds)
        logger.info(f"Inserted/Updated {len(odds)} odds records.")


db_writer = DBWriter()
