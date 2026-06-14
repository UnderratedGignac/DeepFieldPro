---
title: Architecture
tags: [architecture]
---

# 🏗️ Architecture

Back to [[00 - Map of Content]] · Deep dive: [[DEEPFIELD_SYSTEM_ARCHITECTURE]]

## The pipeline (primary stack)
```
betarabia_scraper.py  ──►  data/odds_stream.db  ──►  live_predictions_daemon.py
   (subprocess)              (fixtures+markets)          (the engine loop)
                                                              │
                          models/ (ML artifacts) ◄───────────┤ predict
                                                              ▼
                                          data/todays_dashboard_state.json
                                                              │
                                                              ▼
                              live_dashboard_server.py (Flask)  ──►  Browser UI
```

## Components
- **Scraper** — [[03 - Entry Points & Modules|betarabia_scraper.py]], a background `subprocess.Popen` that writes odds into `odds_stream.db`.
- **Daemon (engine)** — `live_predictions_daemon.py`; loops scrape → fetch fixtures → predict → write state → settle bets.
- **Models** — ML artifacts in `models/` (see [[05 - Configuration]]).
- **Dashboard** — `live_dashboard_server.py` (Flask) serves UI + `/api/*`; starts the daemon thread unless `DEEPFIELD_DISABLE_DAEMON=1`.
- **Execution** — `execution_engine.py` `place_bet()`; SHADOW vs LIVE branch — see [[06 - Safety & Risk]].
- **Arena** — `arena_betting.py`, a Flask blueprint for the Stair-AI World-Cup value-betting page (the only **real-money** path).

## Two separate stacks
1. **Primary (this is what runs)**: Flask dashboard + daemon above.
2. **Newer service stack**: `api/main.py`, `orchestrator.py` (FastAPI/uvicorn) — a different, separate path.

See [[02 - Data Flow]] for the step-by-step, and [[07 - Known Issues & Gotchas]] for why the dashboard may be empty.
