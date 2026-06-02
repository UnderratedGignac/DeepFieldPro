# lineup_sources.py

LINEUP_SOURCES = {
    "official_club_socials": {"reliability": 1.0, "latency_score": 1.0},
    "official_league_feed": {"reliability": 1.0, "latency_score": 0.9},
    "sofascore": {"reliability": 0.95, "latency_score": 0.8},
    "fotmob": {"reliability": 0.95, "latency_score": 0.85},
    "flashscore": {"reliability": 0.9, "latency_score": 0.75},
    "journalist_leak": {"reliability": 0.7, "latency_score": 1.0},
    "expected_predictor": {"reliability": 0.5, "latency_score": 1.0}
}

class LineupSourceRegistry:
    @staticmethod
    def get_source_metrics(source_name: str) -> dict:
        return LINEUP_SOURCES.get(source_name, {"reliability": 0.1, "latency_score": 0.1})

lineup_registry = LineupSourceRegistry()
