import numpy as np
from scipy.stats import nbinom

def calculate_over_prob(p10_passes, p50_passes, p90_passes,
                        p10_minutes, p50_minutes, p90_minutes,
                        betting_line, expected_minutes=90):
    
    minutes_to_use = p50_minutes if expected_minutes == 90 else expected_minutes
    # Protect against 0 minutes
    if minutes_to_use <= 0:
        return 0.01, 0.0
        
    mu = p50_passes * (minutes_to_use / 90.0)
    spread = (p90_passes - p10_passes) * (minutes_to_use / 90.0)
    variance = (spread / 2.56) ** 2

    if variance <= mu:
        from scipy.stats import poisson
        prob_over = 1.0 - poisson.cdf(int(betting_line), mu=mu)
    else:
        r = (mu ** 2) / (variance - mu)
        r = max(r, 0.01)  
        p_nb = r / (r + mu)
        prob_over = 1.0 - nbinom.cdf(int(betting_line), n=r, p=p_nb)

    prob_over = float(np.clip(prob_over, 0.01, 0.99))
    return prob_over, mu

if __name__ == "__main__":
    prob, exp_passes = calculate_over_prob(
        p10_passes=35, p50_passes=45, p90_passes=58,
        p10_minutes=60, p50_minutes=75, p90_minutes=88,
        betting_line=40.5
    )
    print(f"Expected passes: {exp_passes:.1f}")
    print(f"P(over 40.5): {prob:.3f} ({prob*100:.1f}%)")
    print(f"Fair decimal odds: {1/prob:.3f}")
