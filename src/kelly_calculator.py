"""
kelly_calculator.py
-------------------
Correct Kelly Criterion implementation.
- Takes fair_prob directly from model output (not derived from edge)
- Enforces minimum edge threshold before sizing
- Scales Kelly fraction based on model uncertainty (P10/P90 spread)
- Caps at 2% bankroll per bet
"""

import logging

MIN_EDGE_THRESHOLD = 0.03  # 3% minimum edge after vig removal


def fractional_kelly(fair_prob, market_odds, xmin_p10, xmin_p90, expected_mean):
    """
    Calculates Kelly fraction scaled by model uncertainty (P10/P90 spread).

    fair_prob: YOUR model's win probability.
    market_odds: Decimal odds.
    xmin_p10: P10 expected minutes.
    xmin_p90: P90 expected minutes.
    expected_mean: Mean/P50 expected minutes.
    """
    if expected_mean <= 0:
        return 0.0

    # 1. Calculate Uncertainty Spread Percentage
    spread_pct = (xmin_p90 - xmin_p10) / expected_mean

    # 2. Determine Dynamic Kelly Multiplier based on confidence
    if spread_pct < 0.15:
        fraction = 0.25  # High Confidence: Quarter Kelly
    elif spread_pct < 0.30:
        fraction = 0.125  # Moderate Confidence: Eighth Kelly
    else:
        return 0.0  # Low Confidence: Spread >= 30%, DO NOT BET

    # 3. Standard Kelly Formula
    b = market_odds - 1.0
    p = fair_prob
    q = 1.0 - p

    kelly_full = (b * p - q) / b

    if kelly_full <= 0:
        return 0.0

    return kelly_full * fraction


def get_recommended_stake(
    fair_prob, market_odds, current_bankroll, xmin_p10, xmin_p90, expected_mean
):
    """
    Returns the recommended stake in absolute currency.
    Sizing is uncertainty-aware and capped at 2% of bankroll.
    """
    implied_prob = 1.0 / market_odds
    edge = fair_prob - implied_prob

    # Gate: only bet if edge exceeds minimum threshold
    if edge < MIN_EDGE_THRESHOLD:
        return 0.0

    # Calculate uncertainty-aware stake percentage
    stake_pct = fractional_kelly(
        fair_prob, market_odds, xmin_p10, xmin_p90, expected_mean
    )

    # Hard cap: never risk more than 2% on any single bet
    max_single_bet_pct = 0.02
    if stake_pct > max_single_bet_pct:
        stake_pct = max_single_bet_pct

    return round(current_bankroll * stake_pct, 2)


if __name__ == "__main__":
    # Example: model says fair price is 2.00 (50% win prob), book offers 2.15
    # High confidence: spread = (80-70)/75 = 0.133 < 0.15
    stake = get_recommended_stake(0.50, 2.15, 10000, 70, 80, 75)
    print(f"High Confidence Stake: ${stake:.2f}")

    # Moderate confidence: spread = (90-65)/75 = 0.333 > 0.30 (should be $0)
    stake_low = get_recommended_stake(0.50, 2.15, 10000, 65, 90, 75)
    print(f"Low Confidence Stake (should be $0): ${stake_low:.2f}")
