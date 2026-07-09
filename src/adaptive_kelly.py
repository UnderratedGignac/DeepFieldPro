"""
adaptive_kelly.py — Phase 10 (Adaptive Kelly) for DeepFieldPro.

Composite sizing multiplier: Kelly x Calibration Score x Execution Score x
Liquidity Score x Market Quality Score, per the master prompt. Each
sub-score is a simple, documented, config-capped linear scale in [0, 1] —
deliberately simple rather than a fitted model, since the whole point is an
auditable multiplier a human can sanity-check, not another black box.

DESIGN DECISION — missing data never penalizes: calibration and execution
scores depend on live-accumulating history (Phase 4's ECE, Phase 2's
slippage) that is genuinely sparse this early in a tournament (0 settled
Arena bets as of Phase 3/6's findings). When the underlying metric is
unavailable (None), its sub-score defaults to 1.0 (neutral — no penalty),
NOT 0.0. Defaulting to 0 would silently zero out every bet's size the
moment data is thin, which is the opposite of what an "adaptive" sizing
layer should do; a component only pulls sizing DOWN once it has evidence to.

This module is OFF by production default (see arena_betting._load_risk_settings's
"adaptive_kelly_enabled" — defaults to False) until validated with real
settled data; it is a recommend/measure layer per the master prompt, not an
auto-enabled behavior change.
"""


def calibration_score(ece, ece_cap=0.15):
    """
    1.0 at perfect calibration (ece=0), linearly down to 0.0 at ece_cap and
    beyond. None (no calibration data yet, e.g. zero settled bets) -> 1.0
    (neutral, see module docstring).
    """
    if ece is None:
        return 1.0
    if ece_cap <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - ece / ece_cap))


def execution_score(avg_slippage, slippage_cap=0.05):
    """
    1.0 at zero adverse slippage, linearly down to 0.0 at slippage_cap
    (fractional, e.g. 0.05 = 5%) of ADVERSE slippage. Favorable slippage
    (negative, i.e. we paid less than our limit) is capped at 1.0, not
    rewarded above it. None (no fills yet) -> 1.0 (neutral).
    """
    if avg_slippage is None:
        return 1.0
    if slippage_cap <= 0:
        return 1.0
    adverse = max(0.0, avg_slippage)  # only adverse (positive) slippage penalizes
    return max(0.0, min(1.0, 1.0 - adverse / slippage_cap))


def liquidity_score(available_liquidity_usd, desired_usd, required_multiple):
    """
    Ratio of available-to-required order-book depth, capped at 1.0 — same
    "required_multiple x desired size" definition as Phase 2's
    liquidity_gate_ok(), but expressed as a continuous score instead of a
    pass/fail gate (a book with exactly 3x depth scores 1.0; one with 1.5x
    scores 0.5). None/non-positive desired_usd -> 1.0 (nothing being sized
    yet, no penalty to apply).
    """
    if not desired_usd or desired_usd <= 0 or not required_multiple or required_multiple <= 0:
        return 1.0
    required = desired_usd * required_multiple
    if required <= 0:
        return 1.0
    return max(0.0, min(1.0, (available_liquidity_usd or 0.0) / required))


def market_quality_score(vig_pp, vig_cap_pp=10.0):
    """
    1.0 at zero market overround (vig), linearly down to 0.0 at vig_cap_pp
    (percentage points, e.g. 10.0 = 10pp overround — an unusually expensive
    market). Negative vig (a loose/arb-adjacent market) is treated as
    excellent quality, capped at 1.0. None -> 1.0 (neutral, no data).
    """
    if vig_pp is None:
        return 1.0
    if vig_cap_pp <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - max(0.0, vig_pp) / vig_cap_pp))


def adaptive_kelly_multiplier(calibration, execution, liquidity, market_quality):
    """
    Composite multiplier = product of the 4 sub-scores (each already in
    [0, 1]) — multiplicative so a single poor component meaningfully shrinks
    the composite, rather than being averaged away by three good ones.
    """
    return round(calibration * execution * liquidity * market_quality, 6)


def adaptive_kelly_size(base_kelly_usd, calibration, execution, liquidity, market_quality):
    """base_kelly_usd scaled by the composite multiplier above."""
    return round(base_kelly_usd * adaptive_kelly_multiplier(calibration, execution, liquidity, market_quality), 2)
