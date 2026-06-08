# DeepFieldPro User Guide

Updated: 2026-06-08

DeepFieldPro is a football betting research and operations platform. It reads fixture, lineup, player-stat, and odds data; generates model-driven probabilities; compares those probabilities with market prices; and records recommendations, bets, bankroll state, and closing-line value.

This guide is written for local operators. For engineering details, read `README.md` and `SYSTEM_AUDIT_DOCUMENTATION.md`.

## What You Can Do

- View live and upcoming match predictions.
- Track whether predictions were based on official or estimated lineups.
- Monitor recommended markets and estimated edge.
- Review bet logs, bankroll movement, and settlement state.
- Inspect whether the system is receiving odds and fixture data.
- Use the generated documentation to understand the full system architecture.

## Main Ways To Run The System

### Option 1: Windows Launcher

Use this if you want the simplest local startup path:

```bat
LAUNCH_DEEPFIELD.bat
```

Depending on local configuration, the launcher starts the dashboard and related backend scripts.

### Option 2: Live Prediction Daemon

Use this to run the script-oriented local workflow:

```bash
python src/live_predictions_daemon.py
```

The daemon:

1. Starts/refreshes Betarabia odds scraping.
2. Fetches today's fixtures.
3. Checks for official lineups near kickoff.
4. Uses estimated lineups when official lineups are not yet available.
5. Loads model artifacts from `models/`.
6. Writes predictions and dashboard state to local files/databases.
7. Repeats its sweep after a short sleep interval.

### Option 3: Service-Oriented Stack

Use this for the newer acquisition/session/WebSocket architecture:

```bash
python src/database/migrate.py
python src/orchestrator.py
```

Start the API separately when needed:

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Useful endpoints:

- `GET /health`
- `GET /ready`
- `GET /live`
- `GET /metrics`
- `GET /sessions`
- `GET /browser/status`
- `GET /websocket/status`

## What The Dashboard Shows

The dashboard state is stored in files such as `data/todays_dashboard_state.json` and prediction rows in `data/bet_log.db`.

Typical fields include:

- Match name and league
- Kickoff time
- Prediction and expected score
- Match probabilities
- Player or market recommendations
- Whether official lineup data was available
- Odds and estimated expected value where available
- Bet status, settlement, and CLV data

## Data Sources

DeepFieldPro uses multiple sources and caches:

- Betarabia/Kickertech for sportsbook markets
- Sofascore-style endpoints for fixtures, lineups, and stats
- API-Football scripts where credentials and coverage are available
- FBref/soccerdata-style historical player and team data
- Local SQLite databases and CSV files under `data/`
- Model artifacts under `models/`

## Safety And Bankroll Controls

The system includes several risk-control concepts:

- Kelly/fractional sizing
- Bankroll tracking
- No-bet filters
- Stop-loss and exposure logic
- CLV tracking
- Account and market telemetry

Before using real capital, verify:

1. The system is using current odds.
2. Lineups are confirmed or the recommendation is explicitly marked as estimated.
3. The bet log and bankroll DB are updating correctly.
4. Risk limits match your intended bankroll.
5. API keys and credentials are stored in `.env`, not in source code.

## Common Troubleshooting

| Problem | Check |
|---|---|
| No fixtures appear | Verify network/API availability and fixture scraper output. |
| No Betarabia odds | Check `data/betarabia_page_probe.html`, `data/betarabia_screenshot.png`, and `data/odds_stream.db`. |
| Predictions missing | Confirm model files exist under `models/` and source datasets exist under `data/`. |
| Lineups unavailable | The daemon may fall back to estimated lineups until official lineups are released. |
| Dashboard stale | Check `data/todays_dashboard_state.json` timestamp and daemon logs. |
| API unhealthy | Call `/health`, `/ready`, and `/metrics` from the FastAPI service. |

## Important Notes

- This is a research and operations platform, not a guarantee of profit.
- Local SQLite workflows are convenient for development but should be hardened before production use.
- Do not expose the API publicly until authentication and rate limiting are added.
- Do not commit `.env` or sportsbook credentials.
