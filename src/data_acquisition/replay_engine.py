# replay_engine.py
import os
import gzip
import logging
from datetime import datetime, timezone

from .simulation_clock import sim_clock
from .websocket_parser import frame_parser
from .replay_analytics import replay_dashboard

logger = logging.getLogger(__name__)


class ReplayEngine:
    """
    Reconstructs the entire betting market timeline exactly as it happened.
    No future information leakage is permitted.
    """

    def __init__(self, raw_frames_dir: str):
        self.raw_frames_dir = raw_frames_dir
        self.timeline_events = []

    def _load_historical_frames(self, fixture_id: str):
        """
        Loads all archived websocket frames and lineup events for a fixture.
        """
        fixture_dir = os.path.join(self.raw_frames_dir, fixture_id)
        if not os.path.exists(fixture_dir):
            logger.error(f"No raw frames found for {fixture_id} in {fixture_dir}")
            return

        for file_name in sorted(os.listdir(fixture_dir)):
            if file_name.endswith(".json.gz"):
                # Extract timestamp from filename (e.g. 20260602T183316.json.gz)
                time_str = file_name.replace(".json.gz", "")
                try:
                    event_time = datetime.strptime(time_str, "%Y%m%dT%H%M%S%f").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    continue  # Skip malformed filenames

                file_path = os.path.join(fixture_dir, file_name)

                with gzip.open(file_path, "rt", encoding="utf-8") as f:
                    raw_payload = f.read()

                self.timeline_events.append(
                    {
                        "timestamp": event_time,
                        "type": "websocket_frame",
                        "payload": raw_payload,
                        "fixture_id": fixture_id,
                    }
                )

        # Normally we would also load Lineup events from lineup_history here and append to timeline_events

        # Ensure absolute chronological ordering
        self.timeline_events.sort(key=lambda x: x["timestamp"])
        logger.info(f"Loaded {len(self.timeline_events)} historical events for replay.")

    async def run_simulation(self, fixture_id: str):
        """
        Streams events through the simulated infrastructure.
        """
        self._load_historical_frames(fixture_id)

        if not self.timeline_events:
            return

        start_time = self.timeline_events[0]["timestamp"]
        sim_clock.enable_simulation_mode(start_time)

        logger.info(f"--- STARTING REPLAY SIMULATION FOR {fixture_id} ---")

        for event in self.timeline_events:
            # Advance clock precisely to the event timestamp
            sim_clock.advance_to(event["timestamp"])

            if event["type"] == "websocket_frame":
                # Deterministic streaming:
                # Instead of hitting live websocket_parser, we pass the raw payload
                # exactly as it was received.
                canonical_events = frame_parser.parse_frame(
                    event["payload"], event["fixture_id"]
                )

                # In a full simulation, we would emit these to the dynamic_repricer and edge_engine
                for ce in canonical_events:
                    # Mocking the pipeline trigger
                    pass

            elif event["type"] == "lineup_event":
                # Emit to dispatcher
                pass

            # After processing the event, check the execution queue
            # In a real run, the queue would flush to execution_sim.attempt_execution()
            # and results would be logged to replay_dashboard.record_attempt()

        logger.info("--- REPLAY SIMULATION COMPLETE ---")
        sim_clock.disable_simulation_mode()

        # Output final metrics
        replay_dashboard.generate_report()


replay_engine = ReplayEngine(
    "C:/Users/Elie/DeepFieldPro/src/data_acquisition/raw_frames"
)
