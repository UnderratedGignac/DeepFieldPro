"""
bankroll_tracker.py
-------------------
Tracks the system bankroll, enforces daily and total drawdown limits,
and manages the HALT flag.

CONVENTION (critical — must be consistent across all callers):
  - current_balance = liquid cash (money not currently at risk in open bets)
  - register_bet(stake):      deducts stake from current_balance (bet is now "at risk")
  - register_settlement(payout, pnl): adds payout back to current_balance.
      On WIN:  payout = stake * odds, pnl = stake * (odds - 1)
      On LOSS: payout = 0,            pnl = -stake
      On VOID: payout = stake,        pnl = 0

This means: current_balance = cash_in_hand (excludes stakes currently at risk).
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bankroll.db")
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")

STARTING_BANKROLL = 300.0  # paper bankroll seed (overridden at runtime by DB)


def _load_bankroll_limits():
    try:
        with open(_SETTINGS_PATH, "r") as _f:
            _s = json.load(_f)
        return (
            float(_s.get("max_daily_exposure_pct", 0.50)),
            float(_s.get("max_drawdown_pct", 0.30)),
            float(_s.get("daily_stop_loss_pct", 0.50)),
        )
    except Exception:
        return 0.50, 0.30, 0.50


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
        # conn already closed above — don't call conn.close() again
        init_bankroll_db()
        return get_status()  # retry once after auto-init

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
    # Reload limits from settings.json so changes apply without restart
    MAX_DAILY_EXPOSURE_PCT, MAX_DRAWDOWN_PCT, DAILY_STOP_LOSS_PCT = (
        _load_bankroll_limits()
    )

    today = datetime.now(timezone.utc).date().isoformat()
    # BEGIN IMMEDIATE serialises the read-modify-write under SQLite's write lock,
    # preventing two concurrent threads from both passing the exposure cap check.
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT current_balance, daily_exposure, system_status, starting_balance, daily_pnl "
        "FROM bankroll WHERE date = ?",
        (today,),
    )
    row = cursor.fetchone()

    if not row:
        conn.execute("ROLLBACK")
        conn.close()
        init_bankroll_db()
        return register_bet(stake)  # retry once after auto-init

    current_balance, daily_exposure, system_status, starting_balance, daily_pnl = row

    if system_status == "HALT":
        print("System HALTED. No bet registered.")
        conn.execute("ROLLBACK")
        conn.close()
        return False

    # Check daily stop-loss at placement time (not just at settlement).
    # Without this, multiple bets can be placed before any settle, bypassing the gate.
    if starting_balance > 0 and daily_pnl <= -(starting_balance * DAILY_STOP_LOSS_PCT):
        print(
            f"[BANKROLL] Daily stop-loss hit at placement: P&L={daily_pnl:.2f} on "
            f"start={starting_balance:.2f} — no new bets today."
        )
        conn.execute("ROLLBACK")
        conn.close()
        return False

    # Check drawdown limit at placement time as well
    effective_balance = current_balance + daily_exposure  # liquid + at-risk
    if starting_balance > 0:
        drawdown_pct = (starting_balance - effective_balance) / starting_balance
        if drawdown_pct >= MAX_DRAWDOWN_PCT:
            print(
                f"[BANKROLL] Max drawdown reached at placement: "
                f"{drawdown_pct*100:.1f}% >= {MAX_DRAWDOWN_PCT*100:.0f}%"
            )
            conn.execute("ROLLBACK")
            conn.close()
            return False

    # Block bets that would drive the liquid balance negative.
    if stake > current_balance:
        print(
            f"BLOCKED: Stake ${stake:.2f} exceeds current liquid balance ${current_balance:.2f}."
        )
        conn.execute("ROLLBACK")
        conn.close()
        return False

    # Enforce the daily-exposure cap (max % of today's starting balance at risk at once).
    exposure_cap = starting_balance * MAX_DAILY_EXPOSURE_PCT
    if daily_exposure + stake > exposure_cap:
        print(
            f"BLOCKED: Exposure ${daily_exposure + stake:.2f} would exceed daily cap "
            f"${exposure_cap:.2f} ({MAX_DAILY_EXPOSURE_PCT:.0%} of ${starting_balance:.2f})."
        )
        conn.execute("ROLLBACK")
        conn.close()
        return False

    # All checks passed — deduct stake atomically within the IMMEDIATE transaction.
    cursor.execute(
        "UPDATE bankroll SET current_balance = current_balance - ?, "
        "daily_exposure = daily_exposure + ? WHERE date = ?",
        (stake, stake, today),
    )
    conn.execute("COMMIT")
    conn.close()

    print(
        f"Bet registered: ${stake:.2f} deducted. "
        f"Balance: ${current_balance - stake:.2f} | "
        f"Exposure: ${daily_exposure + stake:.2f}"
    )
    return True


def register_settlement(payout, pnl):
    """
    Called AFTER a bet settles.
    payout: Actual money returned to balance (0 for Loss, stake*odds for Win)
    pnl: Net profit/loss (profit for Win, -stake for Loss)
    """
    MAX_DAILY_EXPOSURE_PCT, MAX_DRAWDOWN_PCT, DAILY_STOP_LOSS_PCT = (
        _load_bankroll_limits()
    )

    today = datetime.now(timezone.utc).date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT current_balance, daily_pnl, peak_balance, starting_balance, daily_exposure "
        "FROM bankroll WHERE date = ?",
        (today,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        init_bankroll_db()
        return register_settlement(payout, pnl)  # retry once after auto-init

    current_balance, daily_pnl, peak_balance, starting_balance, daily_exposure = row

    new_balance = current_balance + payout
    new_daily_pnl = daily_pnl + pnl
    # Stake returned to pool on this settlement (WIN: payout-pnl, LOSS: 0-(-stake)=stake, VOID: payout)
    stake_settled = payout - pnl
    # Decrement exposure — stake is no longer at risk after settlement
    remaining_exposure = max(0.0, (daily_exposure or 0.0) - stake_settled)
    effective_balance = new_balance + remaining_exposure
    new_peak = max(peak_balance, effective_balance)
    status = "ACTIVE"

    # Drawdown vs today's starting balance using total portfolio value (not just liquid)
    drawdown_pct = (
        (starting_balance - effective_balance) / starting_balance
        if starting_balance > 0
        else 0
    )
    if drawdown_pct >= MAX_DRAWDOWN_PCT:
        print(
            f"CRITICAL: Drawdown {drawdown_pct*100:.1f}% from today's start "
            f"(${starting_balance:.2f} -> ${effective_balance:.2f}). System HALTED."
        )
        status = "HALT"

    # Check daily stop-loss (settled P&L only, not unrealised open bets)
    if (
        new_daily_pnl <= -(starting_balance * DAILY_STOP_LOSS_PCT)
        and starting_balance > 0
    ):
        print(
            f"CRITICAL: Daily stop-loss hit (${new_daily_pnl:.2f}). "
            f"Halting bets for the rest of today."
        )
        status = "HALT"

    # Write back balance, P&L, peak, status AND updated exposure (prevents cap over-counting)
    cursor.execute(
        """
        UPDATE bankroll
        SET current_balance = ?, daily_pnl = ?, peak_balance = ?,
            system_status = ?, daily_exposure = ?
        WHERE date = ?
    """,
        (new_balance, new_daily_pnl, new_peak, status, remaining_exposure, today),
    )

    conn.commit()
    conn.close()
    print(
        f"Settlement: Payout +${payout:.2f} (Net: ${pnl:+.2f}) | New balance: ${new_balance:.2f}"
    )


if __name__ == "__main__":
    init_bankroll_db()
    print("Bankroll initialized:")
    print(get_status())
