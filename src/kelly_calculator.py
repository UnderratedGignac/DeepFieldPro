"""
kelly_calculator.py
-------------------
Correct Kelly Criterion implementation.
- Takes fair_prob directly from model output (not derived from edge)
- Enforces minimum edge threshold before sizing
- Caps at 2% bankroll per bet
"""

MIN_EDGE_THRESHOLD = 0.03  # Only bet edges > 3% after vig removal

def fractional_kelly(fair_prob, market_odds, fraction=0.25):
    """
    fair_prob:    YOUR model's win probability (e.g., 0.52).
                  This MUST come from your model after vig-stripping the closing line.
    market_odds:  Bookmaker decimal odds you are betting into (e.g., 2.10).
    fraction:     Kelly fraction. 0.25 = quarter Kelly (recommended for sports betting).

    Returns: fraction of bankroll to stake (e.g., 0.018 = 1.8%)
    """
    b = market_odds - 1.0
    p = fair_prob
    q = 1.0 - p

    kelly_full = (b * p - q) / b

    if kelly_full <= 0:
        return 0.0  # No edge, don't bet

    return kelly_full * fraction


def get_recommended_stake(fair_prob, market_odds, current_bankroll, fraction=0.25):
    """
    Returns the recommended stake in absolute currency (e.g., dollars).
    Returns 0 if edge is below the minimum threshold.

    fair_prob:       Model's true win probability.
    market_odds:     Decimal odds offered by the bookmaker.
    current_bankroll: Settled bankroll (liquid capital only).
    """
    implied_prob = 1.0 / market_odds
    edge = fair_prob - implied_prob  # Probability-space edge AFTER vig removal

    # Gate: only bet if edge exceeds minimum threshold
    if edge < MIN_EDGE_THRESHOLD:
        return 0.0

    stake_pct = fractional_kelly(fair_prob, market_odds, fraction)

    # Hard cap: never risk more than 2% on any single bet
    max_single_bet_pct = 0.02
    if stake_pct > max_single_bet_pct:
        stake_pct = max_single_bet_pct

    return current_bankroll * stake_pct


if __name__ == "__main__":
    # Example: model says fair price is 2.00 (50% win prob), book offers 2.15
    fair_prob = 1 / 2.00   # 0.50
    market_odds = 2.15
    bankroll = 10000

    stake = get_recommended_stake(fair_prob, market_odds, bankroll)
    edge = fair_prob - (1 / market_odds)
    print(f"Fair Prob: {fair_prob:.3f} | Market Odds: {market_odds} | Edge: {edge*100:.2f}%")
    print(f"Recommended Stake: ${stake:.2f} ({stake/bankroll*100:.2f}% of bankroll)")

    # Test: below-threshold edge should return $0
    stake_low = get_recommended_stake(0.48, 2.10, bankroll)
    print(f"Below-threshold edge stake (should be $0): ${stake_low:.2f}")
