"""
calibration_metrics.py — Phase 4 (Model Calibration) for DeepFieldPro.

Generic, model-agnostic calibration metrics + optional rescaling, usable on
any (predicted_prob, realized_outcome) pair list — Arena picks, paper 1X2
bets, O/U, whatever. Deliberately has NO dependency on arena_betting.py or
any specific data source; callers assemble the (probs, outcomes) arrays from
whatever history they have (see tools/calibration_report.py for the Arena
wiring) and pass them in.

All functions return a valid, honest result for n=0 (None/empty, not a
fabricated number or a crash) — calibration reports early in a new
tournament will legitimately have too little data to say anything yet.
"""

import numpy as np


def brier_score(probs, outcomes):
    """Mean squared error between predicted probability and binary outcome (0/1). Lower is better."""
    if not probs:
        return None
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    return float(np.mean((p - y) ** 2))


def log_loss(probs, outcomes, eps=1e-12):
    """Binary log loss (cross-entropy). Lower is better. Clips probabilities away from 0/1 to avoid -inf."""
    if not probs:
        return None
    p = np.clip(np.asarray(probs, dtype=float), eps, 1 - eps)
    y = np.asarray(outcomes, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability_bins(probs, outcomes, n_bins=10):
    """
    Bin predictions into n_bins equal-width buckets over [0, 1] and report,
    per non-empty bin: count, average predicted probability, average
    realized outcome (the two data series a reliability diagram plots).
    """
    if not probs:
        return []
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        bins.append(
            {
                "bin_lo": round(float(lo), 3),
                "bin_hi": round(float(hi), 3),
                "n": n,
                "avg_predicted": round(float(p[mask].mean()), 4),
                "avg_actual": round(float(y[mask].mean()), 4),
            }
        )
    return bins


def expected_calibration_error(probs, outcomes, n_bins=10):
    """ECE: sample-weighted average |avg_predicted - avg_actual| across bins."""
    bins = reliability_bins(probs, outcomes, n_bins)
    if not bins:
        return None
    total_n = sum(b["n"] for b in bins)
    return round(
        sum(b["n"] * abs(b["avg_predicted"] - b["avg_actual"]) for b in bins) / total_n, 4
    )


def max_calibration_error(probs, outcomes, n_bins=10):
    """MCE: largest |avg_predicted - avg_actual| gap across any bin (worst-case, not average)."""
    bins = reliability_bins(probs, outcomes, n_bins)
    if not bins:
        return None
    return round(max(abs(b["avg_predicted"] - b["avg_actual"]) for b in bins), 4)


def calibration_summary(probs, outcomes, n_bins=10):
    """Convenience bundle of all four metrics + the reliability bins, for a report/CLI."""
    return {
        "n": len(probs) if probs else 0,
        "brier_score": brier_score(probs, outcomes),
        "log_loss": log_loss(probs, outcomes),
        "ece": expected_calibration_error(probs, outcomes, n_bins),
        "mce": max_calibration_error(probs, outcomes, n_bins),
        "reliability_bins": reliability_bins(probs, outcomes, n_bins),
    }


# ---------------------------------------------------------------------------
# Optional rescaling — fit on a training split, apply to new predictions.
# None of these are wired into production scoring by this Phase; they are
# reporting/what-if tools (per the master prompt: "recommend, don't
# automatically change production"). A human decides whether/when to swap
# a fitted scaler into the live prediction path.
# ---------------------------------------------------------------------------
def fit_platt_scaling(probs, outcomes):
    """
    Platt scaling: fit a 1-D logistic regression on logit(p) -> outcome.
    Returns a callable new_probs = apply(raw_probs). Returns None if there
    isn't enough data (needs both classes present) to fit meaningfully.
    """
    if not probs or len(set(outcomes)) < 2:
        return None
    from sklearn.linear_model import LogisticRegression

    eps = 1e-6
    p = np.clip(np.asarray(probs, dtype=float), eps, 1 - eps)
    logit_p = np.log(p / (1 - p)).reshape(-1, 1)
    y = np.asarray(outcomes, dtype=float)
    model = LogisticRegression()
    model.fit(logit_p, y)

    def apply(raw_probs):
        rp = np.clip(np.asarray(raw_probs, dtype=float), eps, 1 - eps)
        rl = np.log(rp / (1 - rp)).reshape(-1, 1)
        return model.predict_proba(rl)[:, 1].tolist()

    return apply


def fit_isotonic_scaling(probs, outcomes):
    """
    Isotonic regression calibration (non-parametric, monotonic). Returns a
    callable new_probs = apply(raw_probs), or None if there isn't enough
    data to fit.
    """
    if not probs or len(set(outcomes)) < 2:
        return None
    from sklearn.isotonic import IsotonicRegression

    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    model.fit(np.asarray(probs, dtype=float), np.asarray(outcomes, dtype=float))

    def apply(raw_probs):
        return model.predict(np.asarray(raw_probs, dtype=float)).tolist()

    return apply


def fit_temperature_scaling(probs, outcomes):
    """
    Single-parameter temperature scaling for binary probabilities:
    p' = sigmoid(logit(p) / T). T is fit by minimizing log loss via a 1-D
    scalar search (scipy). T > 1 softens overconfident predictions, T < 1
    sharpens underconfident ones. Returns a callable new_probs =
    apply(raw_probs), or None if there isn't enough data.
    """
    if not probs or len(set(outcomes)) < 2:
        return None
    from scipy.optimize import minimize_scalar

    eps = 1e-6
    p = np.clip(np.asarray(probs, dtype=float), eps, 1 - eps)
    logit_p = np.log(p / (1 - p))
    y = np.asarray(outcomes, dtype=float)

    def _loss(T):
        if T <= 0:
            return np.inf
        scaled = 1.0 / (1.0 + np.exp(-logit_p / T))
        scaled = np.clip(scaled, eps, 1 - eps)
        return float(-np.mean(y * np.log(scaled) + (1 - y) * np.log(1 - scaled)))

    result = minimize_scalar(_loss, bounds=(0.05, 20.0), method="bounded")
    T = float(result.x)

    def apply(raw_probs):
        rp = np.clip(np.asarray(raw_probs, dtype=float), eps, 1 - eps)
        rl = np.log(rp / (1 - rp))
        return (1.0 / (1.0 + np.exp(-rl / T))).tolist()

    apply.temperature = T
    return apply
