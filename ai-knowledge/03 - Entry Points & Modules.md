---
title: Entry Points & Modules
tags: [entrypoints]
---

# 🧩 Entry Points & Modules (`src/`)

Back to [[00 - Map of Content]] · Full inventory: [[FILE_INVENTORY_DEEPFIELDPRO]]

| Module | Role |
|---|---|
| `live_dashboard_server.py` | **Flask app**. Serves UI + `/api/*`. Starts daemon thread unless `DEEPFIELD_DISABLE_DAEMON=1`. Port = `DEEPFIELD_PORT` (default 5050). |
| `live_predictions_daemon.py` | **The engine.** `run_daemon()` loop: scrape → fixtures → predict → write state → settle. Holds `fetch_betarabia_odds()`, STAIR-AI integration, the `place_bet()` call site. |
| `free_scraper_module.py` | Sofascore fixture fetch + Betarabia fixture fallback builders. |
| `betarabia_scraper.py` | Background subprocess scraping Betarabia/Kickertech odds into `data/odds_stream.db`. |
| `execution_engine.py` | `place_bet()`; SHADOW vs LIVE branch (LIVE is a placeholder). See [[06 - Safety & Risk]]. |
| `dfp_config.py` | Settings incl. `SHADOW_MODE` (default **True**) and `STAIR_AI_API_KEY`. |
| `free_results_scraper.py` | `get_finished_results()` — free key-less finished scores (ESPN + TheSportsDB). Primary settlement feed. |
| `arena_betting.py` | Stair-AI **World-Cup Arena** value-betting Flask blueprint. The only **real-money** path. |
| `api/main.py`, `orchestrator.py` | Newer FastAPI/uvicorn service stack (separate path). |

## Arena (real money — handle with care)
- Routes: `/arena` standalone + embedded "World Cup Arena" tab. POST `/arena/api/place` only acts with `{"confirm": true}`, **capped $5/order**, wallet buffer, `MAX_BETS_PER_RUN`.
- Bets only when `model_prob >= conf` **and** `model_prob - mid >= edge`. World-Cup-only (season `26618`), before kickoff only.
- API base `https://stair-ai.com`, auth header `x-api-key` (`STAIR_AI_API_KEY` in `.env`).

Related: [[01 - Architecture]] · [[02 - Data Flow]] · [[05 - Configuration]]
