from __future__ import annotations
import os
import sys
import argparse
import subprocess
import json
import datetime
import logging
import sqlite3
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
TODAYS_JSON = os.path.join(DATA_DIR, "todays_single_bets.json")
BET_LOG_CSV = os.path.join(DATA_DIR, "bet_log.csv")


def run_script(script_name, *args, extra_env=None):
    script_path = os.path.join(BASE_DIR, "src", script_name)
    cmd = [sys.executable, script_path] + list(args)
    logger.info(f"Running {script_name}...")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    subprocess.run(cmd, check=True, env=env)


def print_db_health(today_str: str):
    """Print a quick health summary of how many fixtures/markets were scraped for today."""
    db_path = os.path.join(DATA_DIR, "odds_stream.db")
    if not os.path.exists(db_path):
        logger.warning("odds_stream.db not found.")
        return
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Check if kickoff_date column exists
        c.execute("PRAGMA table_info(fixture)")
        cols = {row[1] for row in c.fetchall()}
        has_kd = "kickoff_date" in cols

        if has_kd:
            c.execute(
                "SELECT COUNT(*) FROM fixture WHERE kickoff_date = ? OR (kickoff_date IS NULL AND date(scraped_at)=?)",
                (today_str, today_str),
            )
        else:
            c.execute(
                "SELECT COUNT(*) FROM fixture WHERE date(scraped_at) = ?",
                (today_str,),
            )
        n_fixtures = c.fetchone()[0]

        c.execute(
            """SELECT COUNT(*) FROM market m
               JOIN fixture f ON m.fixture_id = f.fixture_id
               WHERE date(f.scraped_at) = ?""",
            (today_str,),
        )
        n_markets = c.fetchone()[0]
        conn.close()

        print(f"\n── DB HEALTH ({today_str}) ──────────────────────────────────────")
        print(f"   Fixtures in DB  : {n_fixtures}")
        print(f"   Markets in DB   : {n_markets}")
        if n_fixtures == 0:
            print(
                "   ⚠  WARNING: No fixtures found for today — scraper may have been blocked."
            )
        print("────────────────────────────────────────────────────────────────\n")
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")


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


def run_simulation(today_str: str, num_sims: int = 10000) -> str | None:
    """
    For each today's fixture that has player stats in the DB:
      1. Load the home/away player lineup from player_stats
      2. Use SimilarityEngine for any players missing from DB
      3. Run Monte Carlo simulation (10,000 matches)
      4. Save results to data/simulation_results_{today_str}.json
    Returns path to output file, or None on failure.
    """
    db_path = os.path.join(DATA_DIR, "odds_stream.db")
    if not os.path.exists(db_path):
        logger.warning("[Simulator] odds_stream.db not found. Skipping simulation.")
        return None

    try:
        from match_simulator import MatchSimulator
        from similarity_engine import PlayerSimilarityEngine
    except ImportError as e:
        logger.warning(f"[Simulator] Import error: {e}. Skipping simulation.")
        return None

    conn = sqlite3.connect(db_path)
    sim = MatchSimulator(num_simulations=num_sims)
    se = PlayerSimilarityEngine(conn)

    # Load today's fixtures
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT fixture_id, home_team, away_team, kickoff_time, tournament_name
            FROM fixture
            WHERE kickoff_date = ? OR (kickoff_date IS NULL AND date(scraped_at) = ?)
        """,
            (today_str, today_str),
        )
        fixtures = c.fetchall()
    except Exception as e:
        logger.warning(f"[Simulator] Could not load fixtures: {e}")
        conn.close()
        return None

    if not fixtures:
        logger.info("[Simulator] No fixtures found for simulation.")
        conn.close()
        return None

    logger.info(f"[Simulator] Running simulations for {len(fixtures)} fixtures...")
    all_results = []

    for fixture_id, home_team, away_team, kickoff_time, tournament_name in fixtures:
        # Build player list for each team
        def get_players(team_name: str) -> list:
            """Look up players for a team by name match (fuzzy via LIKE)."""
            try:
                rows = conn.execute(
                    """
                    SELECT player_name, position, xg_p90, xa_p90, shots_p90,
                           yellow_cards_p90, minutes_played
                    FROM player_stats
                    WHERE team_id IN (
                        SELECT team_id FROM team_stats
                        WHERE LOWER(team_name) LIKE LOWER(?)
                    )
                    AND minutes_played > 100
                    ORDER BY xg_p90 DESC
                    LIMIT 11
                """,
                    (f"%{team_name}%",),
                ).fetchall()
            except Exception:
                rows = []

            players = []
            for pname, pos, xg, xa, shots, yellow, mins in rows:
                players.append(
                    {
                        "name": pname,
                        "position": pos or "MID",
                        "xg_p90": float(xg or 0),
                        "xa_p90": float(xa or 0),
                        "shots_p90": float(shots or 0),
                        "yellow_p90": float(yellow or 0),
                        "expected_minutes": 75,
                    }
                )
            return players

        home_players = get_players(home_team)
        away_players = get_players(away_team)

        # If fewer than 5 known players per side, fill with similarity engine estimates
        NEEDED = 5
        default_pos_dist = [
            "GK",
            "DEF",
            "DEF",
            "DEF",
            "MID",
            "MID",
            "MID",
            "FWD",
            "FWD",
            "FWD",
            "FWD",
        ]
        for players, team_name in [
            (home_players, home_team),
            (away_players, away_team),
        ]:
            while len(players) < NEEDED:
                idx = len(players)
                pos = default_pos_dist[idx % len(default_pos_dist)]
                est = se.get_estimated_stats(f"{team_name} Player {idx+1}", pos)
                players.append(
                    {
                        "name": est["name"],
                        "position": est["position"],
                        "xg_p90": est.get("xg_p90", 0.05),
                        "xa_p90": est.get("xa_p90", 0.05),
                        "shots_p90": est.get("shots_p90", 1.0),
                        "yellow_p90": est.get("yellow_p90", 0.15),
                        "expected_minutes": 75,
                        "is_synthetic": True,
                        "confidence": est.get("confidence", 10.0),
                    }
                )

        ctx = {
            "home_team": home_team,
            "away_team": away_team,
            "fixture_id": fixture_id,
            "kickoff_time": kickoff_time,
            "tournament_name": tournament_name or "Football",
        }
        try:
            result = sim.simulate_match(home_players, away_players, ctx)
            result["fixture_id"] = fixture_id
            result["kickoff_time"] = kickoff_time
            result["tournament_name"] = tournament_name or "Football"
            all_results.append(result)
            logger.info(
                f"  [{home_team} vs {away_team}] "
                f"Home {result['home_win']}% / Draw {result['draw']}% / Away {result['away_win']}%"
            )
        except Exception as e:
            logger.warning(f"[Simulator] Failed for {home_team} vs {away_team}: {e}")

    conn.close()

    if not all_results:
        return None

    # Save simulation output
    out_path = os.path.join(DATA_DIR, f"simulation_results_{today_str}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "date": today_str,
                "num_simulations": num_sims,
                "fixtures": all_results,
            },
            f,
            indent=2,
        )

    logger.info(f"[Simulator] ✅ Saved simulation results → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run DeepFieldPro prediction pipeline")
    parser.add_argument(
        "--bankroll",
        type=float,
        default=100.0,
        help="Starting bankroll size (default: 100.0)",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=0,
        help="Also scrape fixtures N days ahead of today (default: 0 = today only)",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        default=False,
        help="Run Monte Carlo simulation for today's fixtures using player stats DB",
    )
    parser.add_argument(
        "--sims",
        type=int,
        default=10000,
        help="Number of Monte Carlo simulations per fixture (default: 10000)",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        default=False,
        help="Skip the odds scraping step (use existing DB data)",
    )
    args = parser.parse_args()

    bankroll = args.bankroll
    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    scraper_env = {}
    if args.days_ahead > 0:
        scraper_env["BETARABIA_DAYS_AHEAD"] = str(args.days_ahead)

    # 1. Scrape live odds
    if not args.skip_scrape:
        run_script("betarabia_scraper.py", extra_env=scraper_env)

    # 2. DB health check
    print_db_health(today_str)

    # 3. EV predictor (today's markets only)
    run_script("single_bet_predictor.py", str(bankroll))

    # 4. Parlay builder
    run_script("parlay_builder.py")

    # 5. Generate bets report
    generate_output_file(bankroll)

    # 6. Monte Carlo simulation (optional — runs if --simulate flag or player data exists)
    if args.simulate:
        sim_path = run_simulation(today_str, num_sims=args.sims)
        if sim_path:
            print(f"Simulation results : {sim_path}")
        else:
            print(
                "Simulation         : No player data available yet. Run: python src/data_pipeline.py"
            )
