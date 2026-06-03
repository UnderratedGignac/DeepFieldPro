import logging
import numpy as np

logger = logging.getLogger(__name__)

class MarketMicrostructureEmbeddings:
    """
    Creates dense vector embeddings for leagues, markets, and players based on historical telemetry.
    Useful for clustering, anomaly detection, and discovering structural inefficiencies.
    """
    def __init__(self):
        # Mock embeddings space
        self.embeddings_db = {}

    def generate_embedding(self, market_type: str, player: str, league: str, historical_volatility: float, avg_decay_ms: float) -> np.ndarray:
        """
        Creates a 5-dimensional vector representing the market's hidden sportsbook behavior signature.
        """
        # Dim 1: Volatility factor
        # Dim 2: Decay factor
        # Dim 3: Market type hash
        # Dim 4: Player popularity proxy
        # Dim 5: League liquidity proxy
        
        market_val = sum(ord(c) for c in market_type) % 10 / 10.0
        player_val = sum(ord(c) for c in player) % 10 / 10.0
        league_val = 1.0 if league == "EPL" else 0.5
        
        vec = np.array([
            historical_volatility,
            1.0 / max(0.1, avg_decay_ms / 1000.0),
            market_val,
            player_val,
            league_val
        ])
        
        key = f"{league}_{market_type}_{player}"
        self.embeddings_db[key] = vec
        
        return vec

embeddings_engine = MarketMicrostructureEmbeddings()
