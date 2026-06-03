import os
import sys
import argparse
import subprocess
import json
import datetime
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
TODAYS_JSON = os.path.join(DATA_DIR, "todays_single_bets.json")
BET_LOG_CSV = os.path.join(DATA_DIR, "bet_log.csv")


def run_script(script_name, *args):
    script_path = os.path.join(BASE_DIR, "src", script_name)
    cmd = [sys.executable, script_path] + list(args)
    logger.info(f"Running {script_name}...")
    subprocess.run(cmd, check=True)


def generate_output_file(bankroll: float):
    if not os.path.exists(TODAYS_JSON):
        logger.error("JSON output not found. Pipeline failed.")
        return

    with open(TODAYS_JSON, "r") as f:
        data = json.load(f)

    bets = data.get("bets", [])
    parlays = data.get("parlays", [])

    batch_bets = [b for b in bets if b["status"] == "BATCH"]
    monitor_bets = [b for b in bets if b["status"] == "MONITOR"]

    total_stake = sum(b["kelly_stake"] for b in batch_bets) + sum(
        p["parlay_stake"] for p in parlays
    )
    expected_return = sum(b["kelly_stake"] * b["ev"] for b in batch_bets) + sum(
        p["parlay_stake"] * p["parlay_ev"] for p in parlays
    )

    # Calculate stop-loss remaining
    stop_loss_remaining = bankroll * 0.15  # Default
    if os.path.exists(BET_LOG_CSV):
        try:
            df = pd.read_csv(BET_LOG_CSV)
            settled = df[df["status"] == "SETTLED"].sort_values(
                "timestamp", ascending=False
            )
            if len(settled) > 0:
                RollingPnl_V = settled.head(20)["profit_loss"].sum()
                stop_loss_limit = -0.15 * bankroll
                if RollingPnl_V < 0:
                    stop_loss_remaining = max(0.0, RollingPnl_V - stop_loss_limit)
                else:
                    stop_loss_remaining = abs(stop_loss_limit) + RollingPnl_V
        except Exception:
            pass

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    out_txt_path = os.path.join(DATA_DIR, f"TODAYS_BETS_{today_str}.txt")
    out_json_path = os.path.join(DATA_DIR, f"TODAYS_BETS_{today_str}.json")

    # Save a copy of the JSON
    import shutil

    shutil.copyfile(TODAYS_JSON, out_json_path)

    with open(out_txt_path, "w", encoding="utf-8") as f:
        f.write("================================================================\n")
        f.write("DEEPFIELDPRO — TODAY'S PREDICTIONS\n")
        f.write(f"Date       : {today_str}\n")
        f.write(f"Bankroll   : ${bankroll:.2f}\n")
        f.write(f"Generated  : {data.get('generated_at')}\n")
        f.write("================================================================\n\n")

        f.write("── SINGLE BETS (BATCH — place these) ───────────────────────────\n\n")
        for b in batch_bets:
            fallback_note = (
                " [FALLBACK WARNING: Lower confidence]" if b["is_fallback"] else ""
            )
            f.write(f"#{b['rank']} | {b['fixture']} — {b['kickoff']}\n")
            f.write(f"   Market    : {b['market']}\n")
            f.write(f"   Selection : {b['selection']}\n")
            f.write(f"   Odds      : {b['raw_odds']:.2f}\n")
            f.write(f"   Fair Prob : {b['fair_prob']*100:.1f}% (model estimate)\n")
            f.write(f"   EV        : +{b['ev']*100:.1f}%\n")
            f.write(
                f"   Stake     : ${b['kelly_stake']:.2f} ({b['stake_pct']:.2f}% of bankroll)\n"
            )
            f.write(f"   Confidence: {b['confidence']}\n")
            if fallback_note:
                f.write(f"   Note      :{fallback_note}\n")
            f.write("\n")

        if not batch_bets:
            f.write("   No BATCH single bets today.\n\n")

        f.write("── MONITOR LIST (close to threshold — watch only) ───────────────\n\n")
        for b in monitor_bets:
            f.write(
                f"   {b['fixture']} | {b['market']} | {b['selection']} | Odds: {b['raw_odds']:.2f} | EV: +{b['ev']*100:.1f}%\n"
            )

        if not monitor_bets:
            f.write("   No bets in monitor list.\n")
        f.write("\n")

        f.write("── PARLAYS (BATCH — place these) ────────────────────────────────\n\n")
        for p in parlays:
            f.write(
                f"#{p['rank']} PARLAY | Odds: {p['parlay_odds']:.2f} | EV: +{p['parlay_ev']*100:.1f}%\n"
            )
            for i, leg in enumerate(p["legs"]):
                f.write(f"   Leg {i+1} : {leg} ({p['fixtures'][i]})\n")
            f.write(
                f"   Stake : ${p['parlay_stake']:.2f} ({p['stake_pct']:.2f}% of bankroll)\n\n"
            )

        if not parlays:
            f.write("   No valid BATCH parlays today.\n\n")

        f.write("── PORTFOLIO SUMMARY ────────────────────────────────────────────\n")
        f.write(f"   Total BATCH bets    : {len(batch_bets)}\n")
        f.write(f"   Total BATCH parlays : {len(parlays)}\n")
        f.write(
            f"   Total stake today   : ${total_stake:.2f} ({(total_stake/bankroll)*100:.2f}% of bankroll)\n"
        )
        f.write(f"   Expected return     : ${expected_return:.2f}\n")
        f.write(
            f"   Stop-loss remaining : ${stop_loss_remaining:.2f} before DRAWDOWN_PAUSE triggers\n\n"
        )

        f.write("================================================================\n")
        f.write("RISK DISCLAIMER: This is a model output. All predictions carry\n")
        f.write("uncertainty. Never bet more than you can afford to lose.\n")
        f.write("Paper trade first. Verify odds before placing any bet.\n")
        f.write("================================================================\n")

    print("Scrape complete    : Fixtures and markets processed.")
    print(f"BATCH bets found   : {len(batch_bets)}")
    print(f"BATCH parlays found: {len(parlays)}")
    print(f"Total stake        : ${total_stake:.2f}")
    print(f"Output saved to    : data/TODAYS_BETS_{today_str}.txt")
    print(f"Machine Output     : data/TODAYS_BETS_{today_str}.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run DeepFieldPro prediction pipeline")
    parser.add_argument(
        "--bankroll",
        type=float,
        default=100.0,
        help="Starting bankroll size (default: 100.0)",
    )
    args = parser.parse_args()

    bankroll = args.bankroll

    # 1. Scrape odds
    run_script("betarabia_scraper.py")

    # 2. Compute EV
    run_script("single_bet_predictor.py", str(bankroll))

    # 3. Build parlays
    run_script("parlay_builder.py")

    # 4. Generate report
    generate_output_file(bankroll)
