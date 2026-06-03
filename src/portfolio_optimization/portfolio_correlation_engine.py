import logging
import networkx as nx

logger = logging.getLogger(__name__)


class PortfolioCorrelationEngine:
    """
    Detects hidden exposure overlaps dynamically.
    Instead of static limits, we use a Graph representation of Player/Market/Match relationships.
    """

    def __init__(self):
        self.exposure_graph = nx.Graph()

    def add_exposure(
        self,
        bet_id: str,
        fixture_id: str,
        market_type: str,
        player_name: str,
        stake: float,
    ):
        """
        Adds a new bet into the correlation graph.
        """
        self.exposure_graph.add_node(bet_id, type="bet", stake=stake)

        # Link bet to its underlying drivers
        self.exposure_graph.add_node(fixture_id, type="fixture")
        self.exposure_graph.add_edge(bet_id, fixture_id, weight=1.0)

        if player_name and player_name != "unknown":
            self.exposure_graph.add_node(player_name, type="player")
            self.exposure_graph.add_edge(bet_id, player_name, weight=1.0)

            # Semantic correlation: A player goal prop is highly correlated with the team's over goals
            # In a full implementation, we'd add edges between related markets.
            market_node = f"{fixture_id}_{market_type}"
            self.exposure_graph.add_node(market_node, type="market")
            self.exposure_graph.add_edge(bet_id, market_node, weight=1.0)

    def calculate_correlation_penalty(
        self, fixture_id: str, market_type: str, player_name: str
    ) -> float:
        """
        Calculates how correlated a PROPOSED bet is to existing open exposure.
        Returns a penalty multiplier (1.0 = no correlation, 0.1 = heavily correlated, reduce stake).
        """
        if not self.exposure_graph.has_node(fixture_id):
            return 1.0  # No exposure yet

        # Sum stakes connected to this fixture
        fixture_exposure = sum(  # noqa: F841
            self.exposure_graph.nodes[n].get("stake", 0)
            for n in self.exposure_graph.neighbors(fixture_id)
            if self.exposure_graph.nodes[n].get("type") == "bet"
        )

        # Sum stakes connected to this player
        player_exposure = 0.0
        if player_name and self.exposure_graph.has_node(player_name):
            player_exposure = sum(
                self.exposure_graph.nodes[n].get("stake", 0)
                for n in self.exposure_graph.neighbors(player_name)
                if self.exposure_graph.nodes[n].get("type") == "bet"
            )

        # Example penalty calculation: As exposure grows, penalty increases (multiplier approaches 0)
        # Assuming a hypothetical max exposure tolerance parameter
        max_player_exposure = 500.0

        if player_exposure >= max_player_exposure:
            return 0.0  # Fully saturated

        penalty = 1.0 - (player_exposure / max_player_exposure)

        logger.debug(
            f"[CORRELATION ENGINE] {player_name} in {fixture_id} -> Exposure: ${player_exposure:.2f} | Penalty Multiplier: {penalty:.2f}"
        )
        return max(0.1, penalty)  # Don't go below 0.1 unless fully saturated


correlation_engine = PortfolioCorrelationEngine()
