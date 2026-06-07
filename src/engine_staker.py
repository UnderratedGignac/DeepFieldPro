"""
DeepFieldPro — Stake Sizing Engine (Module 3 of 3)
====================================================
Determines exactly how much to bet on each identified +EV opportunity
using the Fractional Kelly Criterion with dynamic bankroll management.

RISK RULES (institutional grade):
  - Quarter Kelly (25%) — prevents over-betting on variance
  - Hard cap: max 2% of bankroll per single bet
  - Hard cap: max 5% total exposure per match
  - Hard cap: max 10% daily total exposure
  - Drawdown halt: if daily P&L < -5%, stop for the day
  - Never bet with < 3% model edge after vig removal

INPUT:  value_bets_df from engine_bettor.py
        current bankroll (from bankroll_tracker.py DB or manual)
OUTPUT: Final bet slip with exact stake amounts in $

No hardcoded bankroll values in logic. Bankroll is read from DB or passed in.
"""

import pandas as pd
import sqlite3
import os
import sys
import io
from datetime import date

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "bankroll.db")

# ─── Risk Parameters ──────────────────────────────────────────────────────────
KELLY_FRACTION = 0.25  # Quarter Kelly
MAX_SINGLE_BET_PCT = 0.020  # Hard cap: 2% per bet
MAX_PER_MATCH_PCT = 0.050  # Hard cap: 5% across all bets on one match
MAX_DAILY_EXPOSURE_PCT = 0.100  # Hard cap: 10% of bankroll in play at once
MIN_EDGE_TO_BET = 3.0  # Minimum % edge after vig to place a bet
DAILY_STOP_LOSS_PCT = 0.05  # Stop betting if down >5% today


# ─── Bankroll Manager ─────────────────────────────────────────────────────────
def get_or_init_bankroll(starting_bankroll: float = None) -> dict:
    """
    Reads current bankroll from SQLite DB (bankroll_tracker.py schema).
    If DB doesn't exist, initialises it with the provided starting_bankroll.
    Returns dict with current state.
    """
    today = date.today().isoformat()
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS bankroll (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             DATE UNIQUE,
            starting_balance REAL,
            current_balance  REAL,
            peak_balance     REAL,
            daily_exposure   REAL DEFAULT 0,
            daily_pnl        REAL DEFAULT 0,
            system_status    TEXT DEFAULT 'ACTIVE'
        )
    """
    )

    # Try to get today's row
    c.execute("SELECT * FROM bankroll WHERE date = ?", (today,))
    row = c.fetchone()

    if row is None:
        # Get yesterday's closing balance as today's starting
        c.execute(
            "SELECT current_balance, peak_balance FROM bankroll ORDER BY date DESC LIMIT 1"
        )
        prev = c.fetchone()
        if prev:
            start = prev[0]
            peak = max(prev[1], prev[0])
        else:
            start = starting_bankroll or 1000.0
            peak = start

        c.execute(
            """
            INSERT INTO bankroll (date, starting_balance, current_balance, peak_balance, daily_exposure, daily_pnl)
            VALUES (?, ?, ?, ?, 0, 0)
        """,
            (today, start, start, peak),
        )
        conn.commit()

        c.execute("SELECT * FROM bankroll WHERE date = ?", (today,))
        row = c.fetchone()

    cols = [
        "id",
        "date",
        "starting_balance",
        "current_balance",
        "peak_balance",
        "daily_exposure",
        "daily_pnl",
        "system_status",
    ]
    state = dict(zip(cols, row))
    conn.close()
    return state


def update_exposure(additional_stake: float) -> None:
    """Record that we've committed additional_stake to open bets today."""
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE bankroll SET daily_exposure = daily_exposure + ?, current_balance = current_balance - ?
        WHERE date = ?
    """,
        (additional_stake, additional_stake, today),
    )
    conn.commit()
    conn.close()


def record_settlement(pnl: float) -> None:
    """
    Record a settled bet.
    pnl = profit on win (stake × (odds-1)), 0 on loss (stake already deducted), stake on void.
    """
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE bankroll SET daily_pnl = daily_pnl + ?, current_balance = current_balance + ?
        WHERE date = ?
    """,
        (pnl, pnl, today),
    )
    conn.commit()
    conn.close()


# ─── Kelly Calculator ─────────────────────────────────────────────────────────
def kelly_stake_pct(model_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly fraction, then scaled by KELLY_FRACTION (Quarter Kelly).
    Returns fraction of bankroll (e.g., 0.018 = 1.8%).
    Returns 0 if no edge.
    """
    b = decimal_odds - 1.0
    p = model_prob
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0
    return full_kelly * KELLY_FRACTION


def get_stake(
    model_prob: float,
    decimal_odds: float,
    edge_pct: float,
    bankroll_state: dict,
    match_committed_pct: float = 0.0,
) -> dict:
    """
    Calculate exact stake in currency units.

    Parameters
    ----------
    model_prob          : Model's true probability (e.g., 0.55)
    decimal_odds        : Bookmaker decimal odds (e.g., 1.90)
    edge_pct            : Pre-calculated edge % (from betting engine)
    bankroll_state      : Dict from get_or_init_bankroll()
    match_committed_pct : How much % of bankroll already committed to this same match

    Returns dict with:
      stake_pct, stake_amount, risk_level, reason
    """
    current_balance = bankroll_state["current_balance"]
    starting_today = bankroll_state["starting_balance"]
    daily_exposure = bankroll_state["daily_exposure"]
    daily_pnl = bankroll_state["daily_pnl"]
    status = bankroll_state["system_status"]

    reason = None

    # ── Safety gates ──────────────────────────────────────────────────────────
    if status != "ACTIVE":
        return {
            "stake_pct": 0,
            "stake_amount": 0,
            "risk_level": "HALT",
            "reason": f"System halted: {status}",
        }

    if daily_pnl < -(starting_today * DAILY_STOP_LOSS_PCT):
        return {
            "stake_pct": 0,
            "stake_amount": 0,
            "risk_level": "HALT",
            "reason": f"Daily stop-loss hit ({daily_pnl:.2f}). No more bets today.",
        }

    if edge_pct < MIN_EDGE_TO_BET:
        return {
            "stake_pct": 0,
            "stake_amount": 0,
            "risk_level": "NO_EDGE",
            "reason": f"Edge {edge_pct:.1f}% < minimum {MIN_EDGE_TO_BET}%",
        }

    if current_balance <= 0:
        return {
            "stake_pct": 0,
            "stake_amount": 0,
            "risk_level": "BANKRUPT",
            "reason": "Bankroll depleted",
        }

    # ── Kelly sizing ──────────────────────────────────────────────────────────
    raw_pct = kelly_stake_pct(model_prob, decimal_odds)

    # ── Apply hard caps ──────────────────────────────────────────────────────
    # 1. Per-bet cap
    stake_pct = min(raw_pct, MAX_SINGLE_BET_PCT)

    # 2. Per-match cap (reduce if already committed to this match)
    remaining_match_budget = MAX_PER_MATCH_PCT - match_committed_pct
    if remaining_match_budget <= 0:
        return {
            "stake_pct": 0,
            "stake_amount": 0,
            "risk_level": "MATCH_CAP",
            "reason": f"Match exposure cap ({MAX_PER_MATCH_PCT*100:.0f}%) already reached",
        }
    stake_pct = min(stake_pct, remaining_match_budget)

    # 3. Daily exposure cap
    current_exposure_pct = daily_exposure / starting_today if starting_today > 0 else 0
    remaining_daily = MAX_DAILY_EXPOSURE_PCT - current_exposure_pct
    if remaining_daily <= 0:
        return {
            "stake_pct": 0,
            "stake_amount": 0,
            "risk_level": "DAILY_CAP",
            "reason": f"Daily exposure cap ({MAX_DAILY_EXPOSURE_PCT*100:.0f}%) reached",
        }
    stake_pct = min(stake_pct, remaining_daily)

    # ── Final stake in currency ───────────────────────────────────────────────
    stake_amount = current_balance * stake_pct

    # Risk level classification
    if stake_pct >= 0.015:
        risk_level = "HIGH"
    elif stake_pct >= 0.008:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "stake_pct": round(stake_pct * 100, 3),
        "stake_amount": round(stake_amount, 2),
        "kelly_raw": round(raw_pct * 100, 3),
        "risk_level": risk_level,
        "reason": reason or "OK",
        "pot_profit": round(stake_amount * (decimal_odds - 1), 2),
        "pot_loss": round(stake_amount, 2),
        "roi_if_win": round((decimal_odds - 1) * 100, 1),
    }


# ─── Main Stake Sizer ─────────────────────────────────────────────────────────
def run_stake_sizer(
    value_bets_df: pd.DataFrame,
    starting_bankroll: float = None,
) -> pd.DataFrame:
    """
    Takes a DataFrame of identified value bets and assigns exact stake amounts.

    Parameters
    ----------
    value_bets_df    : Output from engine_bettor.run_betting_engine()
    starting_bankroll: Override bankroll for fresh start (optional — will use DB)

    Returns
    -------
    DataFrame: complete bet slip with stake amounts, risk classification,
               expected profit, and all risk gate reasons.
    """
    print(f'\n{"="*65}')
    print("[STAKE SIZER] Calculating optimal bet sizes")
    print(f'{"="*65}')

    if value_bets_df.empty:
        print("  No value bets to size.")
        return pd.DataFrame()

    # Load / initialise bankroll
    bankroll_state = get_or_init_bankroll(starting_bankroll)
    current = bankroll_state["current_balance"]
    print(f"  Current bankroll: ${current:,.2f}")
    print(f'  Daily exposure so far: ${bankroll_state["daily_exposure"]:,.2f}')
    print(f'  Daily P&L: ${bankroll_state["daily_pnl"]:+,.2f}')
    print(f'  System status: {bankroll_state["system_status"]}\n')

    results = []
    # Track per-match committed percentages
    match_committed = {}

    for _, bet in value_bets_df.sort_values("EV %", ascending=False).iterrows():
        match_key = bet.get("Match", "unknown")
        model_prob = float(bet.get("Model Prob", 0))
        decimal_odds = float(bet.get("Book Odds", 0))
        edge = float(bet.get("Edge %", 0))
        committed_so_far = match_committed.get(match_key, 0.0)

        sizing = get_stake(
            model_prob=model_prob,
            decimal_odds=decimal_odds,
            edge_pct=edge,
            bankroll_state=bankroll_state,
            match_committed_pct=committed_so_far / 100.0,
        )

        if sizing["stake_amount"] > 0:
            # Update match tracking
            match_committed[match_key] = committed_so_far + sizing["stake_pct"]

        row = {
            "Player": bet.get("Player", ""),
            "Team": bet.get("Team", ""),
            "Match": match_key,
            "Market": bet.get("Market", ""),
            "Side": bet.get("Side", ""),
            "Book Odds": decimal_odds,
            "Model Prob": f"{model_prob*100:.1f}%",
            "Edge %": f"{edge:.1f}%",
            "EV %": f"{float(bet.get('EV %', 0)):.1f}%",
            "Confidence": bet.get("Confidence", ""),
            "Kelly Raw %": f"{sizing.get('kelly_raw', 0):.2f}%",
            "Stake %": f"{sizing['stake_pct']:.2f}%",
            "Stake $": sizing["stake_amount"],
            "Pot. Profit $": sizing.get("pot_profit", 0),
            "Pot. Loss $": sizing.get("pot_loss", 0),
            "Risk Level": sizing["risk_level"],
            "Gate Status": sizing["reason"],
            "Bet": "✅ BET" if sizing["stake_amount"] > 0 else "❌ SKIP",
        }
        results.append(row)

    slip_df = pd.DataFrame(results)

    # Summary
    bettable = slip_df[slip_df["Bet"] == "✅ BET"]
    total_staked = bettable["Stake $"].sum()
    total_to_win = bettable["Pot. Profit $"].sum()

    print(f"  Bet slip generated: {len(bettable)} bets to place")
    print(
        f"  Total staked:       ${total_staked:,.2f} ({total_staked/current*100:.2f}% of bankroll)"
    )
    print(f"  Potential profit:   ${total_to_win:,.2f}")
    print(f"  Bets skipped:       {len(slip_df) - len(bettable)}")

    return slip_df


if __name__ == "__main__":
    # Demo: run full 3-engine pipeline
    from engine_predictor import run_predictions
    from engine_bettor import run_betting_engine

    # Step 1: Predict
    preds = run_predictions()

    if not preds.empty:
        # Step 2: Identify bets using BetArabia odds (odds_stream.db)
        bets = run_betting_engine(preds)

        # Step 3: Size stakes
        if not bets.empty:
            slip = run_stake_sizer(bets, starting_bankroll=1000.0)
            out = os.path.join(DATA_DIR, f"bet_slip_{date.today()}.csv")
            slip.to_csv(out, index=False)
            print(f"\nBet slip saved: {out}")
            print(
                "\n"
                + slip[
                    [
                        "Player",
                        "Market",
                        "Book Odds",
                        "Model Prob",
                        "Edge %",
                        "Stake $",
                        "Pot. Profit $",
                        "Risk Level",
                        "Bet",
                    ]
                ].to_string(index=False)
            )
