"""
Phase 3 CLI: print the paper-vs-live attribution report against the real
Arena autopilot state. READ-ONLY — loads state via _load_state() and never
calls _save_state() or places any order.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.arena_betting import _load_state, _wallet_kelly_size, get_wallet
from src.attribution_engine import build_attribution_report

state = _load_state()
wallet = get_wallet()
bal = wallet["available_balance_usdc"] if wallet else None

report = build_attribution_report(
    state,
    current_wallet_balance=bal,
    kelly_fn=lambda edge, mid, wb: _wallet_kelly_size(edge, mid, wb),
)

import json
print(json.dumps(report, indent=2))
