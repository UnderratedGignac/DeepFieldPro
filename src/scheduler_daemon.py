import os
import sys
import logging
from datetime import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
from generate_predictions import generate_predictions  # noqa: E402


class PipelineDaemon:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)

    def candidate_scan(self):
        """T-3h Dry Run: Computes fair probabilities and locks targets"""
        logger.info("[DAEMON] Initiating T-3h Candidate Scan...")
        # In a real database we would filter by games kicking off in ~3 hours
        generate_predictions()
        logger.info(
            "[DAEMON] Candidate Scan Complete. Targets locked. Waiting for live odds."
        )

    def final_confirmation(self):
        """T-45m Live Execution: Checks real odds and executes if EV > threshold"""
        logger.info("[DAEMON] Initiating T-45m Final Confirmation & Execution...")

        import json
        import sqlite3

        sys.path.insert(0, os.path.dirname(__file__))
        from clv_updater import fetch_closing_odds_from_api
        from clv_tracker import record_bet

        pred_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "tomorrow_predictions_real.json"
        )
        if not os.path.exists(pred_path):
            logger.error("No predictions found. Did candidate scan run?")
            return

        with open(pred_path, "r") as f:
            predictions = json.load(f)

        db_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "odds_stream.db"
        )
        conn = sqlite3.connect(db_path)

        executed = 0
        for game in predictions:
            match_id = game["fixture_id"]
            for proj in game["player_projections"]:
                play = proj.get("top_ev_play")
                if play and play.get("status") == "WAITING_FOR_LIVE_ODDS":
                    target = play["target_odds_threshold"]

                    # Wire to API
                    live_odds = fetch_closing_odds_from_api(match_id)

                    if live_odds is None:
                        logger.warning(
                            f"  [ODDS] No API odds available for {match_id}. Bet PENDING."
                        )
                        continue

                    # Log into stream
                    conn.execute(
                        "INSERT INTO odds_feed (match_id, market_type, player_id, selection_name, price, bookmaker) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            match_id,
                            play["market"],
                            proj["player"],
                            proj["player"],
                            live_odds,
                            "Pinnacle",
                        ),
                    )
                    conn.commit()

                    if live_odds >= target:
                        ev = (play["fair_prob"] * live_odds) - 1.0
                        play["expected_ev"] = round(ev, 3)
                        play["status"] = "EXECUTED"
                        play["matched_odds"] = live_odds
                        logger.info(
                            f"  [EXECUTE] {proj['player']} {play['market']} @ {live_odds} (EV: {ev:+.1%})"
                        )
                        executed += 1

                        # TASK 4: Record Bet
                        record_bet(
                            PlayerName_P=proj["player"],
                            Market_P=play["market"],
                            EntryOdds_P=live_odds,
                            Stake_P=100.0,  # Dummy stake
                            FairProb_P=play["fair_prob"],
                            TargetThreshold_P=target,
                        )

                    else:
                        play["status"] = "SKIPPED_ODDS_TOO_LOW"
                        logger.info(
                            f"  [SKIP] {proj['player']} {play['market']} | Odds: {live_odds} < Target: {target}"
                        )

        with open(pred_path, "w") as f:
            json.dump(predictions, f, indent=4)
        conn.close()

        logger.info(
            f"[DAEMON] Final Confirmation complete. {executed} orders sent to capital engine."
        )

    def run_daily_settlement(self):
        """Daily job to settle OPEN bets."""
        logger.info("[DAEMON] Running daily bet settlement...")
        from clv_tracker import scan_and_settle

        scan_and_settle()
        logger.info("[DAEMON] Daily bet settlement complete.")

    def on_lineup_change(self, event):
        """Simulated event listener for LineupConfirmedEvent"""
        logger.warning(
            f"[DAEMON ALERT] Lineup change detected for Match {event['match_id']}"
        )
        for player in event["benched_players"]:
            logger.info(f"  -> VOIDING PENDING BATCH ORDERS FOR: {player}")
            logger.info("  -> CAPITAL RELEASED.")

    def recalibrate_platt_scaler(self):
        """Monthly job to recalibrate Platt scaler with latest results"""
        logger.info("[DAEMON] Initiating Monthly Platt Scaler Recalibration...")
        trainer_path = os.path.join(os.path.dirname(__file__), "calibration_trainer.py")
        os.system(f"python {trainer_path}")
        logger.info("[DAEMON] Platt Scaler Recalibration complete.")

    def run(self):
        """Start the async scheduler"""
        logger.info("Starting DeepFieldPro Scheduler Daemon...")

        # Monthly Recalibration Job
        self.scheduler.add_job(
            self.recalibrate_platt_scaler,
            CronTrigger(day=1, hour=3, minute=0),  # noqa: F821
            id="platt_recalibration",
            replace_existing=True,
        )

        # Phase 1: Candidate Generation (T-3h)
        # Using a fixed daily schedule for testing purposes instead of dynamic match times
        self.scheduler.add_job(
            self.candidate_scan,
            CronTrigger(hour=11, minute=30),  # Example: 14:30 games  # noqa: F821
            id="generate_candidates_1",
            replace_existing=True,
        )

        # Phase 2: Live Execution (T-45m)
        self.scheduler.add_job(
            self.final_confirmation,
            CronTrigger(hour=13, minute=45),  # noqa: F821
            id="final_confirmation_1",
            replace_existing=True,
        )

        # Daily settlement job
        self.scheduler.add_job(
            self.run_daily_settlement,
            CronTrigger(hour=23, minute=0),  # noqa: F821
            id="daily_settlement",
            replace_existing=True,
        )

        self.scheduler.start()

        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            self.scheduler.shutdown()


if __name__ == "__main__":
    daemon = PipelineDaemon()

    # Test the mock event watcher
    mock_event = {"match_id": "HTI_NZL_2026", "benched_players": ["Chris Wood"]}
    daemon.on_lineup_change(mock_event)

    # daemon.start() # Commented out so it doesn't block infinitely during testing
