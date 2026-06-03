# -*- coding: utf-8 -*-
"""
pricing_engine.py — DeepFieldPro Probability Calculator
========================================================
Calculates over/under probabilities using Pearson mean normalization
and Negative Binomial distribution.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P
- Variables:  ProperCase suffix _V
- Comments: single line, max 1 line
"""

import numpy as np
from scipy.stats import nbinom, poisson


def calculate_over_prob_pearson(
    p10_passes,
    p50_passes,
    p90_passes,
    p10_minutes,
    p50_minutes,
    p90_minutes,
    betting_line,
    expected_minutes=90,
    opp_ppda=12.0,
    competition_type=0,
):
    """
    Calculate P(Over) using Pearson mean formula with international normalization.

    PearsonMean_V = (p10 + 4*p50 + p90) / 6
    Scaled by expected_minutes and PPDA normalization.
    """
    # Pearson mean from percentile predictions
    PearsonMean_V = (p10_passes + 4 * p50_passes + p90_passes) / 6.0

    # Minutes adjustment
    minutes_to_use = p50_minutes if expected_minutes == 90 else expected_minutes
    if minutes_to_use <= 0:
        return 0.01, 0.0

    # International PPDA normalization
    ClubPpdaBaseline_P = 12.0
    IntlPpdaBaseline_P = 9.5

    if competition_type == 1:
        IntlPpdaNorm_V = opp_ppda / IntlPpdaBaseline_P
        IntlMinutesFactor_V = 72.0 / 82.0  # 0.878
    else:
        IntlPpdaNorm_V = opp_ppda / ClubPpdaBaseline_P
        IntlMinutesFactor_V = 1.0

    # Scale mu by minutes and PPDA
    adjusted_minutes = minutes_to_use * IntlMinutesFactor_V
    mu = PearsonMean_V * (adjusted_minutes / 90.0) * (1.0 / max(IntlPpdaNorm_V, 0.1))

    # Spread for variance estimation
    spread = (p90_passes - p10_passes) * (adjusted_minutes / 90.0)
    variance = (spread / 2.56) ** 2

    # Choose Poisson or Negative Binomial based on variance
    if variance <= mu:
        prob_over = 1.0 - poisson.cdf(int(betting_line), mu=mu)
    else:
        r = (mu**2) / (variance - mu)
        r = max(r, 0.01)
        p_nb = r / (r + mu)
        prob_over = 1.0 - nbinom.cdf(int(betting_line), n=r, p=p_nb)

    prob_over = float(np.clip(prob_over, 0.01, 0.99))
    return prob_over, mu


def calculate_over_prob(
    p10_passes,
    p50_passes,
    p90_passes,
    p10_minutes,
    p50_minutes,
    p90_minutes,
    betting_line,
    expected_minutes=90,
):
    """
    Legacy function for backward compatibility.
    Uses simple linear scaling without Pearson mean.
    """
    minutes_to_use = p50_minutes if expected_minutes == 90 else expected_minutes
    if minutes_to_use <= 0:
        return 0.01, 0.0

    mu = p50_passes * (minutes_to_use / 90.0)
    spread = (p90_passes - p10_passes) * (minutes_to_use / 90.0)
    variance = (spread / 2.56) ** 2

    if variance <= mu:
        prob_over = 1.0 - poisson.cdf(int(betting_line), mu=mu)
    else:
        r = (mu**2) / (variance - mu)
        r = max(r, 0.01)
        p_nb = r / (r + mu)
        prob_over = 1.0 - nbinom.cdf(int(betting_line), n=r, p=p_nb)

    prob_over = float(np.clip(prob_over, 0.01, 0.99))
    return prob_over, mu


if __name__ == "__main__":
    print("Pricing Engine Test")
    print("=" * 50)

    # Test club match
    prob_club, mu_club = calculate_over_prob_pearson(
        p10_passes=35,
        p50_passes=45,
        p90_passes=58,
        p10_minutes=60,
        p50_minutes=75,
        p90_minutes=88,
        betting_line=40.5,
        opp_ppda=12.0,
        competition_type=0,
    )
    print(f"Club Match - Expected: {mu_club:.1f}, P(over 40.5): {prob_club:.3f}")

    # Test international match
    prob_intl, mu_intl = calculate_over_prob_pearson(
        p10_passes=35,
        p50_passes=45,
        p90_passes=58,
        p10_minutes=60,
        p50_minutes=75,
        p90_minutes=88,
        betting_line=40.5,
        opp_ppda=9.5,
        competition_type=1,
    )
    print(f"Intl Match - Expected: {mu_intl:.1f}, P(over 40.5): {prob_intl:.3f}")
