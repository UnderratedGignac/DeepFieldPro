# mypy: ignore-errors
import json
import gzip
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, Any, List
import hashlib

from .market_mapper import market_mapper, MARKET_STATE
from .normalization_engine import normalize_engine

logger = logging.getLogger(__name__)

RAW_FRAMES_DIR = "C:/Users/Elie/DeepFieldPro/src/data_acquisition/raw_frames"
os.makedirs(RAW_FRAMES_DIR, exist_ok=True)


@dataclass
class CanonicalOddsEvent:
    fixture_id: str
    market_type: str
    player_id: str
    player_name: str
    normalized_name: str
    line: float
    side: str
    decimal_odds: float
    implied_probability: float
    status: str
    source: str
    sequence: int
    book_timestamp: str
    received_timestamp: str


class BetarabiaFrameParser:
    FRAME_TYPES = {
        "market_update",
        "odds_update",
        "fixture_update",
        "heartbeat",
        "subscription_ack",
        "market_suspend",
        "market_remove",
        "selection_update",
    }

    def __init__(self):
        # State tracking for delta patching and sequence protection
        # key: selection_id -> dict of latest known state
        self.selection_state_cache: Dict[str, Dict[str, Any]] = {}
        # key: selection_id -> latest sequence number
        self.sequence_tracker: Dict[str, int] = {}
        # Tracking known schemas
        self.known_schemas = set()

    def _archive_raw_frame(self, fixture_id: str, raw_payload: str):
        """Archives compressed raw websocket frames for replay/debugging."""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            # Safety fallback if fixture_id is unknown
            safe_fixture_id = fixture_id if fixture_id else "unknown_fixture"

            fixture_dir = os.path.join(RAW_FRAMES_DIR, safe_fixture_id)
            os.makedirs(fixture_dir, exist_ok=True)

            file_path = os.path.join(fixture_dir, f"{timestamp}.json.gz")
            with gzip.open(file_path, "wt", encoding="utf-8") as f:
                f.write(raw_payload)
        except Exception as e:
            logger.error(f"Failed to archive raw frame: {e}")

    def _fingerprint_schema(self, payload_dict: Dict[str, Any]):
        """Detects new/unknown payload schemas to alert on sportsbook API changes."""
        schema_keys = sorted(payload_dict.keys())
        schema_hash = hashlib.md5("".join(schema_keys).encode("utf-8")).hexdigest()

        if schema_hash not in self.known_schemas:
            self.known_schemas.add(schema_hash)
            logger.info(
                f"Discovered new websocket schema hash [{schema_hash}]. Keys: {schema_keys}"
            )
            # If we wanted to be strict, we could log the full payload to an anomalies folder here

    def _validate_integrity(self, event: CanonicalOddsEvent) -> bool:
        """Validates market integrity before emitting the canonical event."""
        if event.decimal_odds is not None and event.decimal_odds <= 1.0:
            logger.warning(f"Invalid odds <= 1.0 for {event.normalized_name}")
            return False
        if event.implied_probability is not None and (
            event.implied_probability <= 0 or event.implied_probability > 1
        ):
            logger.warning(f"Invalid implied probability for {event.normalized_name}")
            return False
        if event.line is not None and event.line < 0:
            logger.warning(f"Invalid negative line for {event.normalized_name}")
            return False
        if not event.normalized_name:
            logger.warning("Event missing normalized player name.")
            return False
        return True

    def _apply_delta_patch(
        self, selection_id: str, partial_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reconciles partial updates with the known state cache."""
        if selection_id not in self.selection_state_cache:
            self.selection_state_cache[selection_id] = {}

        self.selection_state_cache[selection_id].update(partial_data)
        return self.selection_state_cache[selection_id]

    def parse_frame(
        self, raw_frame: str, fixture_id: str = None
    ) -> List[CanonicalOddsEvent]:
        """
        Main entry point for websocket frame parsing.
        Returns a list of CanonicalOddsEvent objects if valid updates are found.
        """
        # 1. Archive raw frame
        self._archive_raw_frame(fixture_id, raw_frame)

        try:
            data = json.loads(raw_frame)
        except json.JSONDecodeError:
            return []  # Ignore non-JSON frames

        # 2. Schema Discovery
        self._fingerprint_schema(data)

        # 3. Frame Classification
        frame_type = data.get("type", "unknown")
        if frame_type == "heartbeat" or frame_type == "subscription_ack":
            return []  # Ignored operational frames

        received_timestamp = datetime.now(timezone.utc).isoformat()
        book_timestamp = data.get("timestamp", received_timestamp)

        canonical_events = []

        # Determine extraction logic based on frame type.
        # This assumes a structural payload format where updates are in a list.
        updates = data.get("updates", [])

        # If the API sends full market structures
        if "markets" in data:
            updates = data["markets"]
            frame_type = "market_update"

        for update in updates:
            # 4. Sequence Protection
            selection_id = str(update.get("selection_id", update.get("id", "")))
            sequence = update.get("sequence", 0)

            if selection_id:
                last_sequence = self.sequence_tracker.get(selection_id, -1)
                if sequence <= last_sequence and sequence != 0:  # 0 means unsequenced
                    logger.debug(
                        f"Ignoring out-of-order or duplicate frame for {selection_id}. Seq: {sequence} <= {last_sequence}"
                    )
                    continue
                self.sequence_tracker[selection_id] = sequence

            # 5. Delta Update Engine
            full_state = (
                self._apply_delta_patch(selection_id, update)
                if selection_id
                else update
            )

            # Extract market name and map it
            raw_market_name = full_state.get("market_name", data.get("market_name", ""))
            market_type = market_mapper.map_market_name(raw_market_name)
            if not market_type:
                continue

            raw_player_name = full_state.get("player_name", "")
            normalized_name = normalize_engine.normalize_name(raw_player_name)

            # Extract odds
            decimal_odds = full_state.get("odds")
            implied_prob = (
                1.0 / decimal_odds if (decimal_odds and decimal_odds > 0) else 0.0
            )

            status = full_state.get("status", "active").lower()
            if frame_type == "market_suspend":
                status = MARKET_STATE["SUSPENDED"]

            # Construct Event
            event = CanonicalOddsEvent(
                fixture_id=fixture_id or full_state.get("fixture_id", "unknown"),
                market_type=market_type,
                player_id=full_state.get("player_id", selection_id),
                player_name=raw_player_name,
                normalized_name=normalized_name,
                line=full_state.get("line", 0.0),
                side=full_state.get("side", "N/A"),
                decimal_odds=decimal_odds,
                implied_probability=implied_prob,
                status=status,
                source="betarabia",
                sequence=sequence,
                book_timestamp=book_timestamp,
                received_timestamp=received_timestamp,
            )

            # 7. Integrity Validation
            if self._validate_integrity(event):
                canonical_events.append(event)

        return canonical_events


frame_parser = BetarabiaFrameParser()

