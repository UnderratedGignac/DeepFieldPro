---
title: Known Issues & Gotchas
tags: [issues]
---

# ⚠️ Known Issues & Gotchas

Back to [[00 - Map of Content]] · Audit: [[DEEPFIELD_AUDIT_REPORT]]

- **Missing dep**: `pydantic-settings` is required by the daemon — now pinned in `requirements.txt`. See [[05 - Configuration]].
- **Sofascore returns empty** (403 bot-blocked) → fixtures fall back to Betarabia. See [[02 - Data Flow]].
- **Settlement feed**: `free_results_scraper.py` `get_finished_results()` provides free, key-less finished scores (ESPN + TheSportsDB fallback, cached per-date). `settle_open_bets()` uses it as primary; API-Football is only a bonus when quota allows. This is what makes win/loss settlement work.
- **`fetch_betarabia_odds()` was originally undefined** — now implemented in `live_predictions_daemon.py`, returning kickoff/league/status from `odds_stream.db`. **Do NOT revert** the fallback builders to stamping `now()` / `"NS"` / `"Betarabia"` (caused the "all kickoffs show scrape time" glitch).
- **STAIR-AI**: `staging.stair-ai.com` currently fails DNS resolution; STAIR init/orders error out harmlessly. A set API key doesn't help while the host is unreachable.
- **scikit-learn version**: RESOLVED — pinned `1.8.0`; legacy 1.6.1 models re-pickled (`*.sk161.bak` kept). `joblib.load` wrapped in try/except so a bad unpickle degrades instead of crashing.
- **Orphaned port on restart**: a lingering SSE (`/api/stream`) connection can keep the old listening socket alive after the process dies. Workaround: launch on a fresh port via `DEEPFIELD_PORT`. See [[08 - Running the System]].

Related: [[06 - Safety & Risk]] · [[09 - Conventions]]
