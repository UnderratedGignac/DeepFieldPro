import asyncio
import logging
import json
import gzip
import os
import sys
from datetime import datetime, timezone, timedelta

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

# Setup logging to see the full event stream in the console
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from src.data_acquisition.simulation_clock import sim_clock  # noqa: E402
from src.data_acquisition.replay_engine import replay_engine  # noqa: E402
from src.data_acquisition.event_dispatcher import LineupConfirmedEvent, event_dispatcher  # noqa: E402
from src.data_acquisition.dynamic_repricer import repricer  # noqa: E402
from src.data_acquisition.edge_engine import edge_engine  # noqa: E402
from src.data_acquisition.execution_queue import execution_queue  # noqa: E402
from src.data_acquisition.execution_simulator import execution_sim  # noqa: E402
from src.data_acquisition.replay_analytics import replay_dashboard  # noqa: E402
from src.data_acquisition.websocket_parser import CanonicalOddsEvent  # noqa: E402

MOCK_FIXTURE = "MOCK_FIX_1"
RAW_DIR = f"C:/Users/Elie/DeepFieldPro/src/data_acquisition/raw_frames/{MOCK_FIXTURE}"


def generate_mock_data():
    """Generates mock historical websocket frames to test the replay infrastructure."""
    os.makedirs(RAW_DIR, exist_ok=True)

    # Clean previous mock data
    for f in os.listdir(RAW_DIR):
        os.remove(os.path.join(RAW_DIR, f))

    start_time = datetime.now(timezone.utc) - timedelta(hours=2)

    # Frame 1: Initial Odds (No Lineup Yet)
    payload_1 = {
        "type": "market_update",
        "timestamp": start_time.isoformat(),
        "markets": [
            {
                "name": "Player will score a goal",
                "status": "active",
                "selections": [
                    {
                        "player_name": "Bukayo Saka",
                        "odds": 2.50,
                        "line": 0,
                        "side": "N/A",
                        "sequence": 1,
                    }
                ],
            }
        ],
    }

    # Frame 2: Odds drop
    payload_2 = {
        "type": "market_update",
        "timestamp": (start_time + timedelta(seconds=15)).isoformat(),
        "markets": [
            {
                "name": "Player will score a goal",
                "status": "active",
                "selections": [
                    {
                        "player_name": "Bukayo Saka",
                        "odds": 2.20,
                        "line": 0,
                        "side": "N/A",
                        "sequence": 2,
                    }
                ],
            }
        ],
    }

    # Save frames to disk as gzipped json
    for i, payload in enumerate([payload_1, payload_2]):
        ts_str = datetime.fromisoformat(payload["timestamp"]).strftime(
            "%Y%m%dT%H%M%S%f"
        )
        with gzip.open(
            os.path.join(RAW_DIR, f"{ts_str}.json.gz"), "wt", encoding="utf-8"
        ) as f:
            f.write(json.dumps(payload))

    return start_time


async def run_single_match_validation():
    logger.info("=== PHASE 1: SINGLE MATCH REPLAY VALIDATION ===")

    start_time = generate_mock_data()

    # 1. Start Replay Engine to stream the websocket odds
    await replay_engine.run_simulation(MOCK_FIXTURE)

    # 2. Simulate a Lineup Event occurring midway through the timeline
    sim_clock.enable_simulation_mode(start_time + timedelta(seconds=5))

    lineup_payload = {
        "fixture_id": MOCK_FIXTURE,
        "players": [
            {
                "player_name": "Bukayo Saka",
                "starter": True,
                "position": "RW",
                "formation": "4-3-3",
                "team": "Arsenal",
            }
        ],
    }

    # Trigger Event Dispatcher -> Repricer -> Execution Queue
    await event_dispatcher.handle_lineups_confirmed(
        lineup_payload, source="official_club_socials"
    )

    # 3. Trigger Repricer to set fair probabilities

    mock_event = LineupConfirmedEvent(
        MOCK_FIXTURE,
        1.0,
        "official_club_socials",
        False,
        {},
        sim_clock.now().isoformat(),
    )
    await repricer.handle_lineup_event(mock_event, lineup_payload["players"])

    # 4. Process Execution Queue against Simulator
    # Simulating the edge engine catching an edge
    mock_odds_event = CanonicalOddsEvent(
        fixture_id=MOCK_FIXTURE,
        market_type="player_goal_anytime",
        player_id="1",
        player_name="Bukayo Saka",
        normalized_name="bukayo_saka",
        line=0,
        side="N/A",
        decimal_odds=8.00,
        implied_probability=0.125,
        status="active",
        source="betarabia",
        sequence=1,
        book_timestamp=sim_clock.now().isoformat(),
        received_timestamp=sim_clock.now().isoformat(),
    )

    # Mock Edge calculation
    edge_data = edge_engine.evaluate_edge(mock_odds_event, lineup_confidence=0.8)
    if edge_data.get("has_edge"):
        execution_queue.add_to_queue(mock_odds_event, edge_data, approved_stake=100)

    # Flush queue to simulator
    for bet in execution_queue.queue:
        result = execution_sim.attempt_execution(bet, market_volatility=0.8)
        replay_dashboard.record_attempt(result)

    execution_queue.queue.clear()

    # Generate Analytics Report
    replay_dashboard.generate_report()


if __name__ == "__main__":
    asyncio.run(run_single_match_validation())
