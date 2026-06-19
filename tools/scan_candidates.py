"""Show all Arena candidates (qualifying + non-qualifying) to verify ledger count."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.arena_betting import analyze, get_wallet

wallet = get_wallet()
bal = wallet["available_balance_usdc"] if wallet else 0
print(f"Wallet: ${bal:.2f}\n")

all_c = analyze(104, wallet_balance=bal)
qualifying = [c for c in all_c if c["qualifies"]]

print(f"Total candidates (ledger submissions): {len(all_c)}")
print(f"Qualifying (orders placed): {len(qualifying)}")
print()
print(f"{'Q':<2} {'Match':<40} {'Out':<5} {'Model':>6} {'Mid':>6} {'Edge':>8}")
print("-" * 75)
for c in all_c:
    q = "[Q]" if c["qualifies"] else "   "
    print(
        f"{q} {c['match']:<40} {c['outcome']:<5} "
        f"{c['model_prob']*100:>5.1f}%  {c['market_mid']*100:>5.1f}%  "
        f"{c['edge_pp']:>+6.1f}pp"
    )
