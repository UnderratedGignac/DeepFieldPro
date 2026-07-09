"""
edge_threshold_analysis.py — Phase 5 (Edge Analysis) generic metrics.

Pure functions over a sequence of per-bet fractional returns (at flat unit
stake: `price - 1` if won, `-1` if lost) — no dependency on any specific
data source or model. tools/edge_threshold_sweep.py wires this to the
existing walk-forward Dixon-Coles backtest in tools/backtest_1x2_lines.py to
sweep the 2-10% edge thresholds the master prompt asks for.

All functions return None (not a crash, not a fabricated number) when there
isn't enough data to compute a metric meaningfully.
"""

import math


def roi(returns):
    """Mean return per unit staked. None for an empty sequence."""
    if not returns:
        return None
    return sum(returns) / len(returns)


def hit_rate(wins, n):
    return (wins / n) if n else None


def profit_factor(returns):
    """Gross wins / gross losses. None if there are no losses (undefined) or no bets."""
    if not returns:
        return None
    gross_win = sum(r for r in returns if r > 0)
    gross_loss = -sum(r for r in returns if r < 0)
    if gross_loss == 0:
        return None
    return gross_win / gross_loss


def sharpe_ratio(returns):
    """
    Per-bet Sharpe (mean / stdev of returns, NOT annualized — these are
    discrete bet outcomes, not a time series with a fixed period, so an
    annualization factor would be misleading). None if fewer than 2 bets or
    zero variance.
    """
    n = len(returns) if returns else 0
    if n < 2:
        return None
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    if var <= 0:
        return None
    return mean / math.sqrt(var)


def sortino_ratio(returns):
    """Like sharpe_ratio but only penalizes downside variance. None if no losing bets exist."""
    n = len(returns) if returns else 0
    if n < 2:
        return None
    mean = sum(returns) / n
    downside = [min(0.0, r) for r in returns]
    downside_var = sum(d ** 2 for d in downside) / (n - 1)
    if downside_var <= 0:
        return None
    return mean / math.sqrt(downside_var)


def max_drawdown(returns):
    """
    Max peak-to-trough drop in cumulative P&L (flat unit stakes, bets taken
    in the given order — order matters here, unlike the aggregate metrics
    above). Returns a NON-negative number (the size of the worst drawdown),
    or None for an empty sequence.
    """
    if not returns:
        return None
    cum = 0.0
    peak = 0.0
    worst = 0.0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    return round(-worst, 4)


def calmar_ratio(returns):
    """Total return / max drawdown — reward per unit of worst-case pain. None if no drawdown occurred."""
    if not returns:
        return None
    dd = max_drawdown(returns)
    if not dd:
        return None
    return sum(returns) / dd


def kelly_growth_rate(returns, kelly_fraction=0.25):
    """
    Expected log-growth rate of bankroll if every bet were staked at
    `kelly_fraction` of current bankroll (this project's own quarter-Kelly
    convention — see src/arena_betting.py _wallet_kelly_size — used here
    rather than a per-bet-optimal-f Kelly growth figure, since flat-fraction
    Kelly is how this system actually sizes). growth = mean(log(1 + f*r)).
    Returns None if any single bet would bankrupt the fraction (1 + f*r <= 0
    — should not happen for f<=1 and r>=-1, but guarded defensively) or the
    sequence is empty.
    """
    if not returns:
        return None
    logs = []
    for r in returns:
        factor = 1.0 + kelly_fraction * r
        if factor <= 0:
            return None
        logs.append(math.log(factor))
    return sum(logs) / len(logs)


def bootstrap_roi_ci(returns, n_resamples=2000, ci=0.95, rng=None):
    """
    Bootstrap confidence interval on mean ROI via resampling with
    replacement. Returns (lo, hi) or None if fewer than 2 bets. `rng` is an
    injectable random.Random for deterministic tests — defaults to a fresh
    instance (non-deterministic) when not supplied.
    """
    import random

    n = len(returns) if returns else 0
    if n < 2:
        return None
    rng = rng or random.Random()
    means = []
    for _ in range(n_resamples):
        sample = [returns[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1.0 - ci) / 2.0
    lo_idx = int(alpha * n_resamples)
    hi_idx = int((1.0 - alpha) * n_resamples) - 1
    return round(means[max(0, lo_idx)], 4), round(means[min(n_resamples - 1, hi_idx)], 4)


def edge_threshold_metrics(bets, kelly_fraction=0.25):
    """
    `bets`: list of (won: bool, price: float) tuples at flat unit stake.
    Returns the full metrics bundle for one threshold's bet set.
    """
    n = len(bets)
    if n == 0:
        return {
            "n": 0, "roi": None, "hit_rate": None, "sharpe": None, "sortino": None,
            "max_drawdown": None, "calmar": None, "profit_factor": None,
            "kelly_growth": None, "roi_ci_95": None,
        }
    returns = [(price - 1.0) if won else -1.0 for won, price in bets]
    wins = sum(1 for won, _ in bets if won)
    return {
        "n": n,
        "roi": round(roi(returns), 4),
        "hit_rate": round(hit_rate(wins, n), 4),
        "sharpe": round(sharpe_ratio(returns), 4) if sharpe_ratio(returns) is not None else None,
        "sortino": round(sortino_ratio(returns), 4) if sortino_ratio(returns) is not None else None,
        "max_drawdown": max_drawdown(returns),
        "calmar": round(calmar_ratio(returns), 4) if calmar_ratio(returns) is not None else None,
        "profit_factor": round(profit_factor(returns), 4) if profit_factor(returns) is not None else None,
        "kelly_growth": round(kelly_growth_rate(returns, kelly_fraction), 6)
        if kelly_growth_rate(returns, kelly_fraction) is not None else None,
        "roi_ci_95": bootstrap_roi_ci(returns),
    }
