"""
ap2_mandate.py — AP2 (Agent Payments Protocol) SpendingMandate for DeepFieldPro Arena.

Validates every real-money order attempt against configurable spend limits before
the Stair AI POST is made. Loaded as a secondary safety layer inside arena_betting.py;
the primary gate (DEEPFIELD_ARENA_LIVE env var) still runs first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Tuple

_SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"


@dataclass
class SpendingMandate:
    max_per_order: float = 5.0  # hard cap per order
    daily_cap: float = 20.0  # max total real spend per day
    wallet_buffer: float = 10.0  # never touch the last $10 of the wallet
    conf_min: float = 0.55  # require model confidence >= 55%
    edge_min: float = 0.03  # require >= 3% edge vs market
    max_bets_per_run: int = 3  # at most 3 orders per autopilot cycle

    # ------------------------------------------------------------------
    def check(
        self,
        amount: float,
        daily_spent: float,
        wallet_balance: float,
        conf: float = 1.0,
        edge: float = 1.0,
    ) -> Tuple[bool, str]:
        """
        Validate a proposed order.

        Returns (True, "OK") when every check passes, or
        (False, <reason>) when any check fails.  Checks run in order
        so the caller gets the most actionable reason when multiple
        rules are violated.
        """
        if amount <= 0:
            return False, f"amount must be positive (got {amount})"
        if amount > self.max_per_order:
            return (
                False,
                f"order ${amount:.2f} exceeds max_per_order ${self.max_per_order:.2f}",
            )
        if daily_spent + amount > self.daily_cap:
            remaining = max(0.0, self.daily_cap - daily_spent)
            return (
                False,
                f"daily cap ${self.daily_cap:.2f} would be exceeded "
                f"(already spent ${daily_spent:.2f}, remaining ${remaining:.2f})",
            )
        if wallet_balance - amount < self.wallet_buffer:
            safe_max = max(0.0, wallet_balance - self.wallet_buffer)
            return (
                False,
                f"wallet buffer ${self.wallet_buffer:.2f} violated "
                f"(balance ${wallet_balance:.2f}, max safe order ${safe_max:.2f})",
            )
        if conf < self.conf_min:
            return (
                False,
                f"model confidence {conf:.3f} below conf_min {self.conf_min:.3f}",
            )
        if edge < self.edge_min:
            return (
                False,
                f"edge {edge:.4f} below edge_min {self.edge_min:.4f}",
            )
        return True, "OK"

    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, path: Path | str | None = None) -> "SpendingMandate":
        """
        Load from data/settings.json.  Known keys:
            arena_max_per_order, arena_daily_cap, arena_wallet_buffer,
            conf_min, edge_min, max_bets_per_run
        Missing keys fall back to dataclass defaults.
        """
        p = Path(path) if path else _SETTINGS_PATH
        try:
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}

        def _f(key: str, default: float) -> float:
            try:
                v = cfg.get(key)
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        def _i(key: str, default: int) -> int:
            try:
                v = cfg.get(key)
                return int(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        # "arena_max_per_order" takes precedence; "max_per_bet" (arena UI slider key) is the alias
        _max_per_order = _f("arena_max_per_order", None) or _f("max_per_bet", cls.max_per_order)
        return cls(
            max_per_order=_max_per_order,
            daily_cap=_f("arena_daily_cap", cls.daily_cap),
            wallet_buffer=_f("arena_wallet_buffer", cls.wallet_buffer),
            conf_min=_f("conf_min", cls.conf_min),
            edge_min=_f("edge_min", cls.edge_min),
            max_bets_per_run=_i("max_bets_per_run", cls.max_bets_per_run),
        )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_MANDATE = SpendingMandate()
