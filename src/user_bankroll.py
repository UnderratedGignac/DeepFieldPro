"""user_bankroll.py — the user's phone-reported REAL-money balance.

The user replies to a DeepField ntfy notification with a bare number
("100" = $100). The ntfy balance watcher saves it here; every subsequent
pick alert sizes its suggested stake from this balance and then deducts
that suggestion, so the next pick is sized from what's actually left.
The user can resync anytime by sending a fresh number.

Unlike the old day-scoped betarabia_balance (daily_betting_state.json,
which reset to None at midnight UTC), this balance PERSISTS until the
user or a deduction changes it.

Storage: data/user_bankroll.json — {"balance", "updated_at", "history"}.
Pure stdlib; no network.
"""

import datetime
import json
import math
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_FILE = os.path.join(BASE, "data", "user_bankroll.json")
HISTORY_CAP = 200


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load() -> dict:
    try:
        with open(STORE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(state: dict):
    state["history"] = (state.get("history") or [])[-HISTORY_CAP:]
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STORE_FILE)


def get_balance() -> float | None:
    """The user's current tracked real balance, or None if never reported."""
    bal = _load().get("balance")
    try:
        return round(float(bal), 2) if bal is not None else None
    except (TypeError, ValueError):
        return None


def set_balance(amount, source: str = "user", note: str = ""):
    """Overwrite the tracked balance (e.g. from a user's ntfy reply)."""
    amount = float(amount)
    if math.isnan(amount) or math.isinf(amount) or amount < 0:
        raise ValueError(f"invalid balance: {amount}")
    state = _load()
    state["balance"] = round(amount, 2)
    state["updated_at"] = _now_iso()
    state.setdefault("history", []).append(
        {"ts": state["updated_at"], "balance": state["balance"],
         "source": source, "note": note}
    )
    _save(state)
    print(f"[USER_BANKROLL] balance set to ${state['balance']:.2f} (source={source})")


def deduct(amount, note: str = ""):
    """Subtract a suggested stake from the tracked balance (floored at 0).
    No-op if no balance has ever been reported."""
    current = get_balance()
    if current is None:
        return
    new_balance = max(0.0, round(current - float(amount), 2))
    state = _load()
    state["balance"] = new_balance
    state["updated_at"] = _now_iso()
    state.setdefault("history", []).append(
        {"ts": state["updated_at"], "balance": new_balance,
         "source": "deduct", "note": note}
    )
    _save(state)
