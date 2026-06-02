"""
utils.py
--------
Shared utility functions used across the entire pipeline.
- Vig stripping (MUST be applied before any edge calculation)
- Overround calculation
- Decimal/probability conversions
"""


def remove_vig(odds_list):
    """
    Strip bookmaker margin from a set of odds for all outcomes.
    Always call this BEFORE comparing model probability to market odds.

    odds_list: list of decimal odds for all outcomes.
               e.g., [2.10, 1.80] for home/away
               e.g., [3.50, 3.20, 2.10] for 1X2

    Returns:
        fair_probs  : list of vig-free probabilities (sums to 1.0)
        overround   : total implied probability (> 1.0 = bookmaker margin)

    Example:
        odds = [2.10, 1.80]
        implied = [0.476, 0.556] → sum = 1.032  (3.2% overround)
        fair = [0.461, 0.539]    → sum = 1.000
    """
    if not odds_list or any(o <= 0 for o in odds_list):
        raise ValueError("All odds must be positive non-zero values.")

    implied_probs = [1.0 / o for o in odds_list]
    overround = sum(implied_probs)
    fair_probs = [p / overround for p in implied_probs]

    return fair_probs, overround


def implied_prob(decimal_odds):
    """Convert a single decimal odds price to implied probability."""
    if decimal_odds <= 0:
        raise ValueError("Odds must be > 0")
    return 1.0 / decimal_odds


def decimal_to_american(decimal_odds):
    """Convert decimal odds to American moneyline format."""
    if decimal_odds >= 2.0:
        return f"+{int((decimal_odds - 1) * 100)}"
    else:
        return f"{int(-100 / (decimal_odds - 1))}"


def calculate_edge(fair_prob, market_odds):
    """
    Calculate probability-space edge after vig removal.
    fair_prob: your model's win probability (already vig-stripped)
    market_odds: the bookmaker price you are betting into

    Returns: edge as a decimal (e.g., 0.05 = 5%)
    Positive = you have an edge. Negative = book has the edge.
    """
    return fair_prob - implied_prob(market_odds)


if __name__ == "__main__":
    # Test vig removal
    odds = [2.10, 1.80]
    fair_probs, overround = remove_vig(odds)
    print(f"Odds: {odds}")
    print(f"Overround: {overround:.4f} ({(overround-1)*100:.2f}% margin)")
    print(f"Fair probs: {[round(p, 4) for p in fair_probs]}")
    print(f"Sum of fair probs: {sum(fair_probs):.6f}  (should be exactly 1.0)")

    # Test edge calculation
    model_prob = 0.52
    market_price = 2.10
    edge = calculate_edge(model_prob, market_price)
    print(f"\nModel prob: {model_prob} | Market odds: {market_price}")
    print(f"Edge: {edge*100:.2f}%")
