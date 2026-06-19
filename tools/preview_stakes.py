"""Preview what the new tiered Kelly stakes will be on current qualifying picks."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.arena_betting import _wallet_kelly_size, analyze, get_wallet

wallet = get_wallet()
bal = wallet["available_balance_usdc"] if wallet else 81.85
print(f"Wallet: ${bal:.2f} USDC\n")
print(
    f"{'Match':<35} {'Pick':<5} {'Model':>7} {'Market':>7} {'Edge':>6} {'Old($10cap)':>12} {'New($25cap)':>12}"
)
print("-" * 90)

picks = [c for c in analyze(104, wallet_balance=bal) if c["qualifies"]]
for c in picks:
    edge = c["edge"]
    mid = c["market_mid"]
    # old: quarter-Kelly cap $10
    from math import inf

    kf = max(0.0, edge / (1.0 - mid)) if mid < 1 else 0
    old = round(max(1.0, min(kf * 0.25 * bal, bal * 0.20, 10.0)), 2)
    new = _wallet_kelly_size(edge, mid, bal)
    print(
        f"{c['match']:<35} {c['team_code']:<5} {c['model_prob']*100:>6.1f}% {mid*100:>6.1f}% {c['edge_pp']:>+5.1f}pp  ${old:>9.2f}  ${new:>9.2f}"
    )

print(
    f"\nTotal new exposure: ${sum(_wallet_kelly_size(c['edge'],c['market_mid'],bal) for c in picks):.2f}"
)
