# mypy: ignore-errors
BETARABIA_MARKET_MAP = {
    # Goalscorer Markets
    "Anytime Goalscorer": "player_goal_anytime",
    "Player will score a goal": "player_goal_anytime",
    "1st Goalscorer": "player_goal_first",
    "Player will score twice or more": "player_goal_brace",
    "Player will score hat trick or more": "player_goal_hattrick",
    "Player to score in both halves": "player_goal_both_halves",
    "Player to score in first 10 minutes": "player_goal_first_10_mins",
    "Player To Score in 1st Half": "player_goal_first_half",
    "Player To Score in 2nd Half": "player_goal_second_half",
    # Card Markets
    "Player to Receive A Yellow Card": "player_card_yellow",
    "Player to be Carded": "player_card_any",
    "First Player to be Carded": "player_card_first",
    # Shot Markets
    "Player Total Shots": "player_shots_ou",
    "Total Shots": "player_shots_ou",
    "Player Shots On Target": "player_sot_ou",
    "Shots on Target": "player_sot_ou",
    # Offside Markets
    "Player Offsides Totals": "player_offsides_ou",
    "Offsides": "player_offsides_ou",
}

MARKET_STATE = {
    "ACTIVE": "active",
    "SUSPENDED": "suspended",
    "HIDDEN": "hidden",
    "SETTLED": "settled",
    "REMOVED": "removed",
}


class MarketMapper:
    @staticmethod
    def map_market_name(raw_market_name: str) -> str:
        """
        Normalizes a raw sportsbook market name to the canonical DeepFieldPro market key.
        Uses fuzzy matching or direct lookup.
        """
        # Direct match
        if raw_market_name in BETARABIA_MARKET_MAP:
            return BETARABIA_MARKET_MAP[raw_market_name]

        # Case-insensitive direct match
        for key, val in BETARABIA_MARKET_MAP.items():
            if raw_market_name.lower() == key.lower():
                return val

        # If no match is found, we might want to flag it for dynamic discovery
        # but for now, return None to indicate an unsupported market.
        return None


market_mapper = MarketMapper()

