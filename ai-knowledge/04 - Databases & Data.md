---
title: Databases & Data
tags: [data]
---

# 🗄️ Databases & Data (`data/`)

Back to [[00 - Map of Content]] · Producer/consumer flow: [[02 - Data Flow]]

| File | Contents |
|---|---|
| `odds_stream.db` | Scraped fixtures/markets. `fixture`: fixture_id, home_team, away_team, kickoff_time, kickoff_date, league_id, tournament_name, scraped_at. Plus `market`. |
| `bet_log.db` | Bets, parlays, ledger, settlement. |
| `bankroll.db` | Bankroll history. |
| `todays_dashboard_state.json` | **UI source of truth** — current match/prediction state (the array the UI renders). |
| `settings.json` | Runtime UI settings: kelly, EV/confidence thresholds, `auto_place_bets`, etc. |

## Notes for agents
- `odds_stream.db` is **written by** `betarabia_scraper.py` and **read by** the daemon's `fetch_betarabia_odds()`.
- `todays_dashboard_state.json` is **written by** the daemon and **read by** the UI (`GET /api/state`). If it's `[]`, the dashboard is empty — see [[07 - Known Issues & Gotchas]].
- `auto_place_bets` in `settings.json` does **not** actually gate placement — see [[06 - Safety & Risk]].

The `data/` folder is hidden from this Obsidian graph (it's huge), but the files above still exist on disk.
