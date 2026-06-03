# player_position_normalizer.py

POSITION_MAP = {
    "GK": "goalkeeper",
    "CB": "center_back",
    "LCB": "center_back",
    "RCB": "center_back",
    "LB": "fullback",
    "RB": "fullback",
    "LWB": "wingback",
    "RWB": "wingback",
    "CDM": "defensive_mid",
    "CM": "central_mid",
    "CAM": "attacking_mid",
    "LM": "winger",
    "RM": "winger",
    "LW": "winger",
    "RW": "winger",
    "CF": "forward",
    "ST": "striker",
    "SS": "forward",
}


class PlayerPositionNormalizer:
    @staticmethod
    def normalize(raw_position: str) -> str:
        """
        Translates granular or source-specific position strings into
        canonical positional buckets for the Pricing Engine.
        """
        if not raw_position:
            return "unknown"

        clean_pos = raw_position.upper().strip()
        return POSITION_MAP.get(clean_pos, "unknown")


position_normalizer = PlayerPositionNormalizer()
