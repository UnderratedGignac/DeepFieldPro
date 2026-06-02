"""
lineup_monitor.py
-----------------
Polls for lineup confirmation and triggers the full downstream pipeline:
  1. Detects when the lineup payload is populated
  2. Parses the lineup (lineup_parser)
  3. Updates the role baseline (role_baseline_builder)
  4. Detects role shifts (role_shift_detector)
  5. Logs the latency

All processing is done immediately on lineup receipt to maximize
the survival window before the market reprices.
"""

import asyncio
import aiohttp
import os
import csv
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Pipeline imports
from lineup_parser import parse_and_store_lineup, init_db as init_lineup_db
from role_baseline_builder import build_baseline, init_history_db
from role_shift_detector import detect_shifts

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

API_KEY  = os.getenv('API_FOOTBALL_KEY')
API_HOST = 'api-football-v1.p.rapidapi.com'
LOG_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'lineup_latency_log.csv')
POLL_INTERVAL_SECONDS = 5  # 5s poll (requires paid API plan; use 10s on free tier)


def init_log_file():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'match_id', 'kickoff_time', 'expected_lineup_time',
                'lineup_received_at', 'latency_seconds', 'status'
            ])


def log_latency(match_id, kickoff_time, expected_time, received_at, latency, status):
    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            match_id,
            kickoff_time.isoformat(),
            expected_time.isoformat(),
            received_at.isoformat() if received_at else '',
            f"{latency:.2f}" if latency is not None else '',
            status
        ])


async def fetch_lineup(session, fixture_id):
    """Returns the raw API-Football lineup payload, or None if not yet available."""
    url = f"https://{API_HOST}/v3/fixtures/lineups"
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    try:
        async with session.get(url, headers=headers, params={"fixture": str(fixture_id)}) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get('response') and len(data['response']) > 0:
                    return data['response']
    except Exception as e:
        print(f"Fetch error for fixture {fixture_id}: {e}")
    return None


def process_lineup_pipeline(fixture_id, lineup_response):
    """
    Called immediately when lineup is confirmed.
    Runs: parse → update baseline → detect shifts.
    Returns the list of detected role shifts.
    """
    all_shifts = []

    for team_data in lineup_response:
        team_id = str(team_data.get('team', {}).get('id', 'unknown'))
        team_name = team_data.get('team', {}).get('name', team_id)

        # Step 1: Parse and store lineup
        parse_and_store_lineup(str(fixture_id), team_id, team_data)

        # Step 2: Rebuild baseline to include today's data
        build_baseline()

        # Step 3: Detect role shifts for starters only
        starters = []
        for entry in team_data.get('startXI', []):
            p = entry.get('player', {})
            from lineup_parser import POSITION_TO_ROLE
            pos_raw = str(p.get('pos', '')).upper().strip()
            role = POSITION_TO_ROLE.get(pos_raw, 'unknown')
            starters.append({
                'player_id': str(p.get('id', '')),
                'name': p.get('name', 'Unknown'),
                'expected_role': role
            })

        shifts = detect_shifts(starters)
        all_shifts.extend(shifts)

        print(f"  Team {team_name}: {len(starters)} starters parsed | "
              f"{len(shifts)} role shifts detected")

    return all_shifts


async def monitor_match(fixture_id, kickoff_time_str):
    """
    Main monitoring loop. Polls every POLL_INTERVAL_SECONDS seconds
    from 90 minutes before kickoff until lineup is confirmed.

    fixture_id:       API-Football fixture ID (integer)
    kickoff_time_str: ISO format string e.g. "2026-06-05T20:00:00Z"

    Returns list of detected role shifts (for use by execution engine).
    """
    kickoff_time = datetime.fromisoformat(kickoff_time_str.replace("Z", "+00:00"))
    expected_lineup_time = kickoff_time - timedelta(minutes=60)
    start_polling_time   = kickoff_time - timedelta(minutes=90)

    print(f"\n{'='*60}")
    print(f"Fixture:          {fixture_id}")
    print(f"Kickoff:          {kickoff_time.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Expected Lineup:  {expected_lineup_time.strftime('%H:%M UTC')}")
    print(f"Poll Interval:    {POLL_INTERVAL_SECONDS}s")
    print(f"{'='*60}")

    now = datetime.now(timezone.utc)
    if now < start_polling_time:
        wait_seconds = (start_polling_time - now).total_seconds()
        print(f"Standby: {wait_seconds/60:.1f} minutes until polling starts...")
        await asyncio.sleep(wait_seconds)

    print("Polling started...")
    async with aiohttp.ClientSession() as session:
        while True:
            current_time = datetime.now(timezone.utc)

            if current_time > kickoff_time:
                print(f"Kickoff passed without lineup for fixture {fixture_id}.")
                log_latency(fixture_id, kickoff_time, expected_lineup_time, current_time, None, 'failed')
                return []

            lineup = await fetch_lineup(session, fixture_id)
            if lineup:
                received_at = datetime.now(timezone.utc)
                latency_s   = (received_at - expected_lineup_time).total_seconds()

                print(f"\n✅ LINEUP CONFIRMED at {received_at.strftime('%H:%M:%S UTC')} "
                      f"(+{latency_s:.0f}s from expected)")

                log_latency(fixture_id, kickoff_time, expected_lineup_time,
                            received_at, latency_s, 'success')

                # Trigger the full pipeline immediately
                shifts = process_lineup_pipeline(fixture_id, lineup)

                window_remaining = (kickoff_time - received_at).total_seconds()
                print(f"\n⏱  Survival window remaining: {window_remaining:.0f}s until kickoff")
                print(f"Role shifts to act on: {len([s for s in shifts if s.get('apply_to_model')])}")

                from model_runner import run_for_match

                # Extract the two team names from the lineup response
                team_names = [t.get('team', {}).get('name', 'Unknown') for t in lineup]
                home_team = team_names[0] if len(team_names) > 0 else 'Unknown'
                away_team = team_names[1] if len(team_names) > 1 else 'Unknown'

                # Run once for each team, using the other as the opponent
                all_bets = []
                for team_data in lineup:
                    my_team = team_data.get('team', {}).get('name', 'Unknown')
                    opp_team = away_team if my_team == home_team else home_team
                    bets = run_for_match(
                        fixture_id      = fixture_id,
                        opponent_team   = opp_team,
                        lineup_drop_at  = received_at.isoformat(),
                        latency_ms      = int(latency_s * 1000),
                        role_shifts     = shifts,
                        regime          = 'lineup_adjustment_window'
                    )
                    all_bets.extend(bets)

                print(f"Total bets placed this match: {len(all_bets)}")

                return shifts

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    # Initialize all required DBs before running
    init_log_file()
    init_lineup_db()
    init_history_db()

    # ── Replace these with a real fixture to test ──
    # asyncio.run(monitor_match(1035049, "2026-06-04T19:45:00Z"))
    print("lineup_monitor.py ready.")
    print("Call: asyncio.run(monitor_match(fixture_id, '2026-06-04T19:45:00Z'))")
