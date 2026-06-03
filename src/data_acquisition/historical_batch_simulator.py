import asyncio
import logging
import json
import gzip
import os
import random
import sys
from datetime import datetime, timezone, timedelta

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

logging.basicConfig(
    level=logging.WARNING
)  # Suppress info to prevent flooding, only show report
logger = logging.getLogger(__name__)

from src.data_acquisition.simulation_clock import sim_clock  # noqa: E402
from src.data_acquisition.replay_engine import replay_engine  # noqa: E402
from src.data_acquisition.event_dispatcher import LineupConfirmedEvent  # noqa: E402
from src.data_acquisition.dynamic_repricer import repricer  # noqa: E402
from src.data_acquisition.edge_engine import edge_engine  # noqa: E402
from src.data_acquisition.execution_queue import execution_queue  # noqa: E402
from src.data_acquisition.execution_simulator import execution_sim  # noqa: E402
from src.data_acquisition.replay_analytics import replay_dashboard  # noqa: E402
from src.data_acquisition.websocket_parser import CanonicalOddsEvent  # noqa: E402

RAW_DIR = "C:/Users/Elie/DeepFieldPro/src/data_acquisition/raw_frames"

MARKETS = [
    "player_goal_anytime",
    "player_shots_ou",
    "player_sot_ou",
    "player_card_yellow",
]
SOURCES = [
    ("official_club_socials", 1.0),
    ("sofascore", 0.95),
    ("journalist_leak", 0.7),
    ("expected_predictor", 0.5),
]


def generate_batch_data(num_matches=50):
    fixtures = []
    logger.warning(f"Generating {num_matches} simulated historical fixtures...")

    for i in range(num_matches):
        fixture_id = f"BATCH_FIX_{i}"
        fixtures.append(fixture_id)

        fix_dir = os.path.join(RAW_DIR, fixture_id)
        os.makedirs(fix_dir, exist_ok=True)
        for f in os.listdir(fix_dir):
            os.remove(os.path.join(fix_dir, f))

        start_time = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))

        # We simulate the odds "decaying" rapidly. Initial frame has mispriced odds.
        # Volatility dictates how likely the book is to suspend/reject.
        volatility = random.uniform(0.1, 0.9)  # noqa: F841

        # Frame 1: Initial Mispriced Odds
        market_name = random.choice(MARKETS)
        initial_odds = random.uniform(2.5, 4.0)

        payload_1 = {
            "type": "market_update",
            "timestamp": start_time.isoformat(),
            "markets": [
                {
                    "name": market_name,
                    "status": "active",
                    "selections": [
                        {
                            "player_name": f"Player_{i}",
                            "odds": initial_odds,
                            "line": 0,
                            "side": "N/A",
                            "sequence": 1,
                        }
                    ],
                }
            ],
        }

        # Save to disk
        ts_str = start_time.strftime("%Y%m%dT%H%M%S%f")
        with gzip.open(
            os.path.join(fix_dir, f"{ts_str}.json.gz"), "wt", encoding="utf-8"
        ) as f:
            f.write(json.dumps(payload_1))

    return fixtures


async def run_batch_simulation(fixtures: list):
    logger.warning("=== PHASE 2: HISTORICAL BATCH VALIDATION ===")

    # Temporarily set analytics logger to INFO so we see the report
    logging.getLogger("src.data_acquisition.replay_analytics").setLevel(logging.INFO)

    for i, fixture_id in enumerate(fixtures):
        # 1. Run engine to parse raw frames
        await replay_engine.run_simulation(fixture_id)

        # 2. Simulate a lineup drop
        source_name, conf = random.choice(SOURCES)
        sim_clock.enable_simulation_mode(
            sim_clock.now() + timedelta(seconds=random.randint(0, 120))
        )

        lineup_payload = {
            "fixture_id": fixture_id,
            "players": [
                {
                    "player_name": f"Player_{i}",
                    "starter": True,
                    "position": "RW",
                    "formation": "4-3-3",
                    "team": "Team A",
                }
            ],
        }

        # Only process if it's an official source (to simulate real flow, though we bypass checks here for test density)
        mock_event = LineupConfirmedEvent(
            fixture_id, conf, source_name, False, {}, sim_clock.now().isoformat()
        )
        await repricer.handle_lineup_event(mock_event, lineup_payload["players"])

        # 3. Queue logic
        market_type = random.choice(MARKETS)
        volatility = random.uniform(0.1, 0.9)
        time_since = random.randint(0, 90)  # seconds since lineup

        # Realistic odds (2.0 to 4.0). We force fair_prob to create artificial EV for testing.
        odds = random.uniform(2.0, 4.0)
        repricer.fair_price_cache[fixture_id] = {
            market_type: {
                f"player_{i}": (1.0 / odds) + random.uniform(0.01, 0.15)
            }  # 1% to 15% edge
        }

        mock_odds_event = CanonicalOddsEvent(
            fixture_id=fixture_id,
            market_type=market_type,
            player_id=str(i),
            player_name=f"Player_{i}",
            normalized_name=f"player_{i}",
            line=0,
            side="N/A",
            decimal_odds=odds,
            implied_probability=1.0 / odds,
            status="active",
            source="betarabia",
            sequence=1,
            book_timestamp=sim_clock.now().isoformat(),
            received_timestamp=sim_clock.now().isoformat(),
        )

        edge_data = edge_engine.evaluate_edge(mock_odds_event, lineup_confidence=conf)

        if edge_data.get("has_edge"):
            execution_queue.add_to_queue(mock_odds_event, edge_data, approved_stake=100)

        # Flush queue
        for bet in execution_queue.queue:
            # We pass the metadata down for analytics
            bet["confidence"] = conf
            bet["time_since_lineup"] = time_since

            result = execution_sim.attempt_execution(bet, market_volatility=volatility)

            # Enrich result for analytics
            result["market"] = bet["market"]
            result["confidence"] = bet["confidence"]
            result["time_since_lineup"] = bet["time_since_lineup"]

            replay_dashboard.record_attempt(result)

        execution_queue.queue.clear()

    logger.warning("All matches simulated. Generating final report.")
    replay_dashboard.generate_report()


if __name__ == "__main__":
    fixtures = generate_batch_data(50)
    asyncio.run(run_batch_simulation(fixtures))
