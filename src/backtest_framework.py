"""
backtest_framework.py — Phase 11 (Backtest Framework) for DeepFieldPro.

Ties together the metrics already built in Phase 5 (src/edge_threshold_analysis.py
— ROI, Sharpe, Sortino, max drawdown, Calmar, profit factor, Kelly growth,
bootstrap ROI CI) with a new Monte Carlo bankroll projection, into one
`full_backtest_report()` call — deliberately NOT re-implementing any of the
Phase 5 primitives (see edge_threshold_analysis.py).

"Same code path as production" scope note (verify assumptions, per the
master prompt): the walk-forward glue in tools/backtest_framework_report.py
fits and predicts using src/models/dixon_coles.py's `fit_league` /
`predict_1x2_from_params` -- the SAME model module src/arena_betting.py and
src/live_predictions_daemon.py import in production, not a reimplementation.
It does NOT re-simulate arena_betting.py's full live decision pipeline
(Forebet gate, drawdown tiers, liquidity gate, adaptive Kelly) against
historical Polymarket order books, because no such historical WC2026
Polymarket archive exists to replay against -- the tournament is live and
current. That gap is stated here rather than papered over with a fabricated
historical Arena simulation.

No-look-ahead-bias note: Monte Carlo resampling (below) draws WITH
replacement from an already-realized, already-out-of-sample bet sequence
(e.g. Phase 5/8's held-out test-season bets) — it projects forward from real
history, it does not use any information a bettor wouldn't have had when
each bet in that history was placed.
"""

import random

from src.edge_threshold_analysis import edge_threshold_metrics


def monte_carlo_projection(
    returns, n_sims=2000, n_bets=None, starting_bankroll=1.0,
    kelly_fraction=0.25, ruin_threshold=0.5, rng=None,
):
    """
    Resample WITH replacement from `returns` (per-bet fractional returns at
    flat unit stake, same convention as edge_threshold_analysis) `n_bets`
    times per simulation (default: len(returns)), compounding a bankroll at
    `kelly_fraction` sizing each bet, repeated `n_sims` times.

    Returns median/p5/p95 ending bankroll (relative to starting_bankroll=1.0
    by default), and prob_of_ruin = fraction of simulations ending below
    `ruin_threshold` x starting_bankroll (default: lost more than half).

    None if `returns` is empty (nothing to resample from) — not a crash, not
    a fabricated projection.
    """
    if not returns:
        return None
    n_bets = n_bets or len(returns)
    rng = rng or random.Random()
    n = len(returns)
    endings = []
    ruin_count = 0
    for _ in range(n_sims):
        bankroll = starting_bankroll
        for _ in range(n_bets):
            r = returns[rng.randrange(n)]
            factor = 1.0 + kelly_fraction * r
            bankroll *= max(0.0, factor)  # bankroll cannot go negative
            if bankroll <= 0:
                break
        endings.append(bankroll)
        if bankroll < starting_bankroll * ruin_threshold:
            ruin_count += 1
    endings.sort()
    return {
        "n_sims": n_sims,
        "n_bets_per_sim": n_bets,
        "median_ending_bankroll": round(endings[n_sims // 2], 4),
        "p5_ending_bankroll": round(endings[int(0.05 * n_sims)], 4),
        "p95_ending_bankroll": round(endings[min(n_sims - 1, int(0.95 * n_sims))], 4),
        "prob_of_ruin": round(ruin_count / n_sims, 4),
        "ruin_threshold": ruin_threshold,
        "kelly_fraction": kelly_fraction,
    }


def full_backtest_report(bets, kelly_fraction=0.25, n_sims=2000, rng=None):
    """
    `bets`: list of (won: bool, price: float) tuples at flat unit stake —
    same shape edge_threshold_analysis.edge_threshold_metrics() takes.

    Returns the Phase 5 metrics bundle plus a Monte Carlo bankroll
    projection, so this single call covers every metric the master prompt's
    Phase 11 lists (ROI, Sharpe, Sortino, Calmar, max drawdown, profit
    factor, Kelly growth, Monte Carlo, bootstrap CI).
    """
    metrics = edge_threshold_metrics(bets, kelly_fraction=kelly_fraction)
    if metrics["n"] == 0:
        return {**metrics, "monte_carlo": None}
    returns = [(price - 1.0) if won else -1.0 for won, price in bets]
    mc = monte_carlo_projection(returns, n_sims=n_sims, kelly_fraction=kelly_fraction, rng=rng)
    return {**metrics, "monte_carlo": mc}
