---
title: Data Flow
tags: [data-flow]
---

# 🔁 Data Flow — how a match reaches the dashboard

Back to [[00 - Map of Content]] · Architecture: [[01 - Architecture]]

1. **Scrape** — `betarabia_scraper.py` (background subprocess) writes fixtures + markets into `data/odds_stream.db` (tables `fixture`, `market`). See [[04 - Databases & Data]].
2. **Fetch fixtures** — the daemon calls `get_todays_fixtures()` → Sofascore. ⚠️ **Sofascore frequently returns empty** (403 bot-blocked).
3. **Fallback** — on empty, `fetch_betarabia_odds()` reads `odds_stream.db` `fixture` rows → dict keyed by `"Home vs Away"` carrying `{kickoff, league, status}`. Fallback builders turn these into fixture dicts.
4. **Predict + write** — daemon runs the models, then writes **`data/todays_dashboard_state.json`** (the array the UI shows).
5. **Serve** — UI reads `GET /api/state`; live updates stream via `GET /api/stream` (SSE).

## Key rule
**Empty dashboard ⇒ the daemon isn't running, or the state file is `[]`.**
The UI alone never populates matches.

> ⚠️ Don't revert the fallback builders to stamping `now()` / `"NS"` / `"Betarabia"` —
> that caused the "all kickoffs show the scrape time" bug. See [[07 - Known Issues & Gotchas]].
