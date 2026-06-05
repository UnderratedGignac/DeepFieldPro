"""
bankroll_tracker.py
-------------------
Tracks the system bankroll, enforces daily and total drawdown limits,
and manages the HALT flag.

CONVENTION (critical — must be consistent across all callers):
  - current_balance = liquid cash (money not currently at risk in open bets)
  - register_bet(stake):      deducts stake from current_balance (bet is now "at risk")
  - register_settlement(pnl): adds settlement back to current_balance.
      On WIN:  pnl = stake * (odds - 1)       → adds only the profit
      On LOSS: pnl = 0                         → stake was already deducted, nothing to add back
      On VOID: pnl = stake                     → refund the stake that was deducted

This means: current_balance = cash_in_hand (excludes stakes currently at risk).
"""

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bankroll.db")

# ─────────────────────────────────────────────────────────
# Configuration — Edit these to match your actual bankroll
# ─────────────────────────────────────────────────────────
STARTING_BANKROLL = 100.0  # Your initial capital
MAX_DAILY_EXPOSURE_PCT = 0.10  # Max 10% of today's starting balance at risk at once
MAX_DRAWDOWN_PCT = 0.20  # -20% from peak → full global halt
DAILY_STOP_LOSS_PCT = 0.05  # -5% in one day  → halt for the day


def init_bankroll_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS bankroll (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        date             DATE UNIQUE,
        starting_balance REAL,
        current_balance  REAL,
        peak_balance     REAL,
        daily_exposure   REAL,
        daily_pnl        REAL,
        system_status    TEXT DEFAULT 'ACTIVE'
    )
    """
    )

    today = datetime.now(timezone.utc).date().isoformat()
    cursor.execute(
        "SELECT current_balance, peak_balance FROM bankroll ORDER BY id DESC LIMIT 1"
    )
    last_row = cursor.fetchone()

    if not last_row:
        # First ever run
        cursor.execute(
            """
            INSERT INTO bankroll (date, starting_balance, current_balance, peak_balance, daily_exposure, daily_pnl)
            VALUES (?, ?, ?, ?, 0.0, 0.0)
        """,
            (today, STARTING_BANKROLL, STARTING_BANKROLL, STARTING_BANKROLL),
        )
    else:
        cursor.execute("SELECT id FROM bankroll WHERE date = ?", (today,))
        if not cursor.fetchone():
            last_balance, last_peak = last_row
            cursor.execute(
                """
                INSERT INTO bankroll (date, starting_balance, current_balance, peak_balance, daily_exposure, daily_pnl)
                VALUES (?, ?, ?, ?, 0.0, 0.0)
            """,
                (today, last_balance, last_balance, last_peak),
            )

    conn.commit()
    conn.close()


def get_status():
    """Returns current bankroll state for today. Returns HALT if DB not ready."""
    today = datetime.now(timezone.utc).date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT current_balance, daily_exposure, system_status, peak_balance, starting_balance "
        "FROM bankroll WHERE date = ?",
        (today,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "status": "HALT",
            "reason": "DB not initialized. Run init_bankroll_db() first.",
        }

    current_balance, daily_exposure, system_status, peak_balance, starting_balance = row
    return {
        "status": system_status,
        "current_balance": current_balance,
        "daily_exposure": daily_exposure,
        "peak_balance": peak_balance,
        "starting_balance": starting_balance,
    }


def register_bet(stake):
    """
    Called BEFORE a bet is placed. Checks limits, then deducts stake from balance.
    Returns True if the bet can proceed, False if it was blocked.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT current_balance, daily_exposure, system_status, starting_balance "
        "FROM bankroll WHERE date = ?",
        (today,),
    )
    row = cursor.fetchone()

    if not row:
        print(
            "ERROR: Bankroll not initialized for today. Call init_bankroll_db() first."
        )
        conn.close()
        return False

    current_balance, daily_exposure, system_status, starting_balance = row

    if system_status == "HALT":
        print("System HALTED. No bet registered.")
        conn.close()
        return False

    # Check max daily exposure limit
    max_exposure = starting_balance * MAX_DAILY_EXPOSURE_PCT
    if (daily_exposure + stake) > max_exposure:
        print(
            f"WARNING: Bet of ${stake:.2f} would exceed daily exposure limit "
            f"(${daily_exposure:.2f} + ${stake:.2f} > ${max_exposure:.2f}). "
            f"Halting further bets today."
        )
        cursor.execute(
            "UPDATE bankroll SET system_status = 'HALT' WHERE date = ?", (today,)
        )
        conn.commit()
        conn.close()
        return False

    # Check sufficient balance
    if stake > current_balance:
        print(
            f"WARNING: Stake ${stake:.2f} exceeds current liquid balance ${current_balance:.2f}."
        )
        conn.close()
        return False

    # All checks passed — deduct stake
    cursor.execute(
        "UPDATE bankroll SET current_balance = ?, daily_exposure = ? WHERE date = ?",
        (current_balance - stake, daily_exposure + stake, today),
    )
    conn.commit()
    conn.close()

    print(
        f"Bet registered: ${stake:.2f} deducted. "
        f"Balance: ${current_balance - stake:.2f} | "
        f"Exposure: ${daily_exposure + stake:.2f}"
    )
    return True


def register_settlement(pnl):
    """
    Called AFTER a bet settles.

    pnl convention:
      WIN:  pnl = stake * (odds - 1)   → profit only (stake already deducted)
      LOSS: pnl = 0                     → nothing to add (stake already gone)
      VOID: pnl = stake                 → full refund of deducted stake

    Checks drawdown and daily stop-loss after every settlement.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT current_balance, daily_pnl, peak_balance, starting_balance "
        "FROM bankroll WHERE date = ?",
        (today,),
    )
    row = cursor.fetchone()
    if not row:
        print("ERROR: No bankroll record for today.")
        conn.close()
        return

    current_balance, daily_pnl, peak_balance, starting_balance = row

    new_balance = current_balance + pnl
    new_daily_pnl = daily_pnl + pnl
    new_peak = max(peak_balance, new_balance)
    status = "ACTIVE"

    # Check peak-to-valley drawdown
    drawdown_pct = (new_peak - new_balance) / new_peak if new_peak > 0 else 0
    if drawdown_pct >= MAX_DRAWDOWN_PCT:
        print(
            f"🛑 CRITICAL: Peak drawdown {drawdown_pct*100:.1f}% reached. System GLOBALLY HALTED."
        )
        status = "HALT"

    # Check daily stop-loss
    if new_daily_pnl <= -(starting_balance * DAILY_STOP_LOSS_PCT):
        print(
            f"🛑 CRITICAL: Daily stop-loss hit (${new_daily_pnl:.2f}). "
            f"Halting bets for the rest of today."
        )
        status = "HALT"

    cursor.execute(
        """
        UPDATE bankroll
        SET current_balance = ?, daily_pnl = ?, peak_balance = ?, system_status = ?
        WHERE date = ?
    """,
        (new_balance, new_daily_pnl, new_peak, status, today),
    )

    conn.commit()
    conn.close()
    print(
        f"Settlement: +${pnl:.2f} | New balance: ${new_balance:.2f} | "
        f"Daily P&L: ${new_daily_pnl:.2f}"
    )


if __name__ == "__main__":
    init_bankroll_db()
    print("Bankroll initialized:")
    print(get_status())
