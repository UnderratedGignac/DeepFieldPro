"""
Preview Arena stake sizing: old (pre-Phase-1, 40%-of-wallet floor) vs new
(pure configurable Kelly) vs new-with-drawdown-applied.

READ-ONLY: loads autopilot state via _load_state() for the drawdown snapshot
but never calls _save_state() — this script must never mutate production
state or place any order. Safe to run against the live wallet at any time.
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.arena_betting import (
    _wallet_kelly_size,
    _load_risk_settings,
    _update_drawdown_state,
    _load_state,
    analyze,
    get_wallet,
    MIN_USD_PER_BET,
    MAX_USD_PER_BET,
)

wallet = get_wallet()
bal = wallet["available_balance_usdc"] if wallet else 81.85
print(f"Wallet: ${bal:.2f} USDC\n")

risk = _load_risk_settings()

# Read-only snapshot of today's drawdown tier — copy the state dict so this
# preview can never accidentally persist a start_balance snapshot itself.
state = _load_state()
import copy

dd_info = _update_drawdown_state(copy.deepcopy(state), bal, risk)
print(
    f"Drawdown: {dd_info['drawdown_pct'] * 100:.1f}%  |  "
    f"Kelly multiplier: {dd_info['kelly_multiplier']:.2f}  |  "
    f"Directional bets disabled: {dd_info['disable_directional']}\n"
)

print(
    f"{'Match':<35} {'Pick':<5} {'Model':>7} {'Market':>7} {'Edge':>6} "
    f"{'Old(40% floor)':>15} {'New(pure Kelly)':>17} {'New(w/ drawdown)':>17}"
)
print("-" * 130)

picks = [c for c in analyze(104, wallet_balance=bal) if c["qualifies"]]
total_old = total_new = total_dd = 0.0
for c in picks:
    edge = c["edge"]
    mid = c["market_mid"]

    # Old behavior (removed in Phase 1): quarter-Kelly, then floored to 40% of
    # wallet for Forebet-confirmed/arb picks, capped at $100/order.
    kf = max(0.0, edge / (1.0 - mid)) if mid < 1 else 0.0
    kelly_suggestion = kf * 0.25 * bal
    floor_size = bal * 0.40
    old = round(min(max(kelly_suggestion or MIN_USD_PER_BET, floor_size), MAX_USD_PER_BET), 2)

    # New: pure Kelly, configurable fraction, no floor.
    new = _wallet_kelly_size(
        edge, mid, bal, kelly_fraction=risk["kelly_fraction"],
        min_usd=risk["minimum_bet"], max_usd=risk["maximum_bet"],
    )
    # New with today's drawdown multiplier applied (what autopilot_cycle()
    # would actually use right now, absent the arb-bypass / block check).
    new_dd = _wallet_kelly_size(
        edge, mid, bal, kelly_fraction=risk["kelly_fraction"],
        min_usd=risk["minimum_bet"], max_usd=risk["maximum_bet"],
        dd_multiplier=dd_info["kelly_multiplier"],
    )

    total_old += old
    total_new += new
    total_dd += new_dd
    blocked = dd_info["disable_directional"] and not c.get("real_arb")
    dd_label = f"${new_dd:>7.2f}{'  [BLOCKED]' if blocked else ''}"
    print(
        f"{c['match']:<35} {c['team_code']:<5} {c['model_prob']*100:>6.1f}% "
        f"{mid*100:>6.1f}% {c['edge_pp']:>+5.1f}pp  ${old:>13.2f}  ${new:>15.2f}  {dd_label}"
    )

print(f"\nTotal old (40%-floor) exposure: ${total_old:.2f}")
print(f"Total new (pure Kelly) exposure: ${total_new:.2f}")
print(f"Total new (w/ drawdown) exposure: ${total_dd:.2f}  "
      f"(picks marked [BLOCKED] would be skipped entirely by autopilot_cycle(), "
      f"not staked at this amount)")
