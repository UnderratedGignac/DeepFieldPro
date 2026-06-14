import os
import csv
import uuid
import datetime
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BET_LOG_CSV = os.path.join(DATA_DIR, "bet_log.csv")
DB_ODDS = os.path.join(DATA_DIR, "odds_stream.db")


def init_csv():
    if not os.path.exists(BET_LOG_CSV):
        with open(BET_LOG_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "bet_id",
                    "timestamp",
                    "player_name",
                    "market",
                    "entry_odds",
                    "stake",
                    "fair_prob",
                    "target_threshold",
                    "closing_odds",
                    "clv",
                    "outcome",
                    "profit_loss",
                    "status",
                ]
            )


def record_bet(
    PlayerName_P, Market_P, EntryOdds_P, Stake_P, FairProb_P, TargetThreshold_P
):
    init_csv()
    bet_id = str(uuid.uuid4())[:8]
    timestamp = datetime.datetime.now().isoformat()
    with open(BET_LOG_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                bet_id,
                timestamp,
                PlayerName_P,
                Market_P,
                EntryOdds_P,
                Stake_P,
                FairProb_P,
                TargetThreshold_P,
                "",
                "",
                "",
                "",
                "OPEN",
            ]
        )
    return bet_id


def settle_bet(BetId_P, ClosingOdds_P, Outcome_P):
    init_csv()
    rows = []
    found = False

    with open(BET_LOG_CSV, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["bet_id"] == BetId_P and row["status"] == "OPEN":
                entry_odds = float(row["entry_odds"])
                stake = float(row["stake"])

                clv = (entry_odds / float(ClosingOdds_P)) - 1.0
                profit_loss = (
                    (stake * entry_odds - stake) if Outcome_P == "WIN" else -stake
                )

                row["closing_odds"] = ClosingOdds_P
                row["clv"] = clv
                row["outcome"] = Outcome_P
                row["profit_loss"] = profit_loss
                row["status"] = "SETTLED"
                found = True
            rows.append(row)

    if found:
        with open(BET_LOG_CSV, "w", newline="") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)


def generate_report():
    if not os.path.exists(BET_LOG_CSV):
        print("No bet_log.csv found.")
        return

    df = pd.read_csv(BET_LOG_CSV)
    settled = df[df["status"] == "SETTLED"]

    if settled.empty:
        print("No settled bets to report.")
        return

    total_bets = len(settled)
    win_rate = (len(settled[settled["outcome"] == "WIN"]) / total_bets) * 100
    total_pl = settled["profit_loss"].sum()
    total_staked = settled["stake"].sum()
    roi = (total_pl / total_staked) * 100 if total_staked > 0 else 0
    avg_clv = settled["clv"].mean() * 100
    avg_entry = settled["entry_odds"].mean()
    avg_closing = settled["closing_odds"].mean()

    print("\n" + "=" * 50)
    print("=== CLV & P&L REPORT ===")
    print("=" * 50)
    print(f"Total Settled Bets: {total_bets}")
    print(f"Win Rate:           {win_rate:.1f}%")
    print(f"Total P&L:          ${total_pl:.2f}")
    print(f"ROI:                {roi:.1f}%")
    print(
        f"Average CLV:        +{avg_clv:.1f}%"
        if avg_clv > 0
        else f"Average CLV:        {avg_clv:.1f}%"
    )
    print(f"Avg Entry Odds:     {avg_entry:.2f}")
    print(f"Avg Closing Odds:   {avg_closing:.2f}")
    print("-" * 50)

    print("P&L by Market Type:")
    mkt_pl = settled.groupby("market")["profit_loss"].sum()
    for mkt, pl in mkt_pl.items():
        print(f"  {mkt:<20}: ${pl:.2f}")

    print("-" * 50)

    print("Rolling 10-bet P&L (Latest first):")
    recent_pnl = (
        settled.sort_values("timestamp", ascending=False).head(10)["profit_loss"].values
    )
    print("  " + " | ".join([f"${p:.2f}" for p in recent_pnl]))
    print("=" * 50)


def scan_and_settle():
    """Daily job function to read odds_stream.db for outcomes and auto-settle OPEN bets."""
    if not os.path.exists(BET_LOG_CSV) or not os.path.exists(DB_ODDS):
        return

    df = pd.read_csv(BET_LOG_CSV)
    open_bets = df[df["status"] == "OPEN"]

    if open_bets.empty:
        return

    conn = sqlite3.connect(DB_ODDS)
    cursor = conn.cursor()  # noqa: F841

    # In a real system, we'd look up the match outcome
    # For now, we mock looking up a settled outcome
    for _, bet in open_bets.iterrows():
        # Mocking settlement logic for backtest purposes
        import random

        mock_closing = float(bet["entry_odds"]) * random.uniform(0.9, 1.05)
        mock_outcome = "WIN" if random.random() < float(bet["fair_prob"]) else "LOSS"
        settle_bet(bet["bet_id"], round(mock_closing, 2), mock_outcome)

    conn.close()


if __name__ == "__main__":
    generate_report()
